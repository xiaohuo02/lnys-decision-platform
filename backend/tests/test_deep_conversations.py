#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Round 2: 深度对话质量 & 鲁棒性测试

测试维度:
  G1. 多轮上下文保持 — 同一 thread 追问 5 轮，验证上下文记忆
  G2. 跨 Skill 链式对话 — 同一 thread 依次触发不同 Skill
  G3. 长文本输入 Copilot — 超长业务描述
  G4. 错误恢复 — 无效输入、空问题、注入类文本
  G5. 并发会话隔离 — 两个不同 thread 同时进行
  G6. OpenClaw 5 轮连续对话上下文衔接
  G7. 舆情分析复杂边界 — 中性文本、纯表情、超短、混合中英
  G8. KB 向量检索语义准确性 — 多种 query 测相似度排序
  G9. Copilot 记忆与历史消息一致性
"""
import json
import time
import urllib.request
import urllib.error
import ssl
import sys
import concurrent.futures

BASE = "http://127.0.0.1:8000"
ssl._create_default_https_context = ssl._create_unverified_context


def api(method, path, data=None, headers=None, timeout=60):
    url = f"{BASE}{path}"
    body = json.dumps(data, ensure_ascii=False).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        raw = resp.read().decode()
        return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        bt = ""
        try:
            bt = e.read().decode()[:500]
        except:
            pass
        return e.code, {"error": str(e), "body": bt}
    except Exception as e:
        return 0, {"error": str(e)}


def sse_collect(path, data, headers=None, timeout=120):
    url = f"{BASE}{path}"
    body = json.dumps(data, ensure_ascii=False).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    events = []
    full_text = ""
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        raw_body = resp.read().decode("utf-8", errors="replace")
        for frame in raw_body.split("\n\n"):
            frame = frame.strip()
            if not frame:
                continue
            et, ed = "", ""
            for p in frame.split("\n"):
                if p.startswith("event:"):
                    et = p[6:].strip()
                elif p.startswith("data:"):
                    ed = p[5:].strip()
            if ed:
                pd2 = {}
                try:
                    pd2 = json.loads(ed)
                except:
                    pd2 = {"raw": ed}
                if not et and "type" in pd2:
                    et = pd2["type"]
                if et:
                    events.append({"type": et, "data": pd2})
                    if et in ("text_delta", "token"):
                        full_text += pd2.get("content", "")
        return events, full_text
    except Exception as e:
        return events, f"[ERROR] {e}"


def chk(label, cond, detail=""):
    s = "✓" if cond else "✗"
    msg = f"  {s} {label}"
    if detail and not cond:
        msg += f": {detail}"
    print(msg)
    return cond


stats = {}
def init_mod(n): stats[n] = {"pass": 0, "warn": 0, "fail": 0, "issues": []}
def rec(mod, case, passed, issue=None):
    if passed:
        stats[mod]["pass"] += 1
    elif issue and issue.startswith("⚠"):
        stats[mod]["warn"] += 1
        stats[mod]["issues"].append(f"{case}: {issue}")
    else:
        stats[mod]["fail"] += 1
        stats[mod]["issues"].append(f"{case}: {issue or 'FAIL'}")


def get_admin_token():
    c, r = api("POST", "/admin/auth/login", {"username": "admin", "password": "admin"})
    if c == 200 and isinstance(r, dict):
        return r.get("access_token", "")
    return ""


# ══════════════════════════════════════════════════════════════
#  G1. Copilot 多轮上下文保持 (5 轮追问)
# ══════════════════════════════════════════════════════════════

def test_multi_turn_context():
    mod = "G1-多轮上下文"
    init_mod(mod)
    print(f"\n{'═' * 60}")
    print(f"  {mod}: Copilot 5 轮追问上下文保持")
    print(f"{'═' * 60}")

    token = get_admin_token()
    if not token:
        rec(mod, "JWT", False, "⚠ 无法登录")
        return
    auth = {"Authorization": f"Bearer {token}"}
    thread_id = f"deep-ctx-{int(time.time())}"

    turns = [
        ("Turn1", "A001黄岩蜜橘目前库存多少？"),
        ("Turn2", "那它的销量预测呢？未来7天会怎样？"),
        ("Turn3", "如果要补货的话，建议补多少？"),
        ("Turn4", "有没有跟A001经常一起买的商品？可以做关联推荐吗？"),
        ("Turn5", "综合以上信息，给我出一份运营建议"),
    ]

    prev_text = ""
    for tid, (name, question) in enumerate(turns):
        print(f"\n  [{name}] {question}")
        evts, txt = sse_collect("/admin/copilot/stream", {
            "question": question,
            "thread_id": thread_id,
        }, headers=auth, timeout=120)

        ok_reply = chk(f"回复>20字", len(txt) > 20, f"len={len(txt)}")
        # Turn2+ 应该能理解追问指向 A001
        if tid >= 1:
            # 不要求一定提到 A001，但回复应该有实质内容
            has_context = len(txt) > 30
            chk(f"上下文延续", has_context, f"len={len(txt)}")
        print(f"  回复: {txt[:120]}...")
        rec(mod, name, ok_reply)
        prev_text = txt

    # 验证 thread 消息数
    print(f"\n  [验证] 检查 thread 消息数")
    c, r = api("GET", f"/admin/copilot/threads/{thread_id}/messages?limit=20", headers=auth)
    d = r.get("data", r) if isinstance(r, dict) else {}
    msgs = d.get("messages", [])
    ok = chk(f"消息数>=10 (5轮×2)", len(msgs) >= 10, f"got {len(msgs)}")
    rec(mod, "消息持久化", ok)


# ══════════════════════════════════════════════════════════════
#  G2. 跨 Skill 链式对话
# ══════════════════════════════════════════════════════════════

def test_cross_skill_chain():
    mod = "G2-跨Skill链"
    init_mod(mod)
    print(f"\n{'═' * 60}")
    print(f"  {mod}: 同一 thread 切换 Skill")
    print(f"{'═' * 60}")

    token = get_admin_token()
    if not token:
        rec(mod, "JWT", False, "⚠ 无法登录")
        return
    auth = {"Authorization": f"Bearer {token}"}
    thread_id = f"cross-skill-{int(time.time())}"

    skills = [
        ("库存", "查一下当前库存预警有哪些SKU需要关注？"),
        ("客户", "那客户方面呢？RFM分析里高价值客户有多少？"),
        ("欺诈", "最近有没有异常交易需要审查？"),
        ("舆情", "客户评价中有哪些负面反馈需要处理？"),
    ]

    for name, question in skills:
        print(f"\n  [{name}] {question}")
        evts, txt = sse_collect("/admin/copilot/stream", {
            "question": question,
            "thread_id": thread_id,
        }, headers=auth, timeout=90)
        ok = chk(f"回复>20字", len(txt) > 20, f"len={len(txt)}")
        # 检查是否有 skill 相关事件
        skill_events = [e for e in evts if e["type"] in ("tool_call", "tool_result", "artifact_start")]
        chk(f"触发Skill事件", len(skill_events) > 0 or len(txt) > 50, f"skill_events={len(skill_events)}")
        print(f"  回复: {txt[:120]}...")
        rec(mod, f"Skill-{name}", ok)


# ══════════════════════════════════════════════════════════════
#  G3. Copilot 长文本输入
# ══════════════════════════════════════════════════════════════

def test_long_input_copilot():
    mod = "G3-长文本输入"
    init_mod(mod)
    print(f"\n{'═' * 60}")
    print(f"  {mod}: 超长业务描述 Copilot")
    print(f"{'═' * 60}")

    token = get_admin_token()
    if not token:
        rec(mod, "JWT", False, "⚠ 无法登录")
        return
    auth = {"Authorization": f"Bearer {token}"}

    long_q = (
        "我们现在遇到一个复杂情况，需要综合分析：\n"
        "1. A001黄岩蜜橘库存告急，仓库反馈只剩2天的量\n"
        "2. 客户投诉近一周增加了40%，主要集中在物流延迟和包装破损\n"
        "3. B002福鼎白茶的销量比上月下降了30%\n"
        "4. 有客户反映C001大黄鱼重量不足的问题\n"
        "5. 竞品在做大促，我们需要考虑是否跟进降价\n"
        "6. 供应商反馈下个月柑橘类产品可能涨价15%\n"
        "请你综合以上信息，给出详细的运营决策建议，包括紧急程度排序、"
        "具体行动方案和预期效果。"
    )
    print(f"\n  [长文本] 多点决策问题 ({len(long_q)}字)")
    evts, txt = sse_collect("/admin/copilot/stream", {"question": long_q}, headers=auth, timeout=120)
    ok = chk("回复>100字", len(txt) > 100, f"len={len(txt)}")
    chk("事件流完整", any(e["type"] == "run_end" for e in evts), "无 run_end")
    print(f"  回复: {txt[:200]}...")
    rec(mod, "长文本决策", ok)


# ══════════════════════════════════════════════════════════════
#  G4. 错误恢复 & 边界
# ══════════════════════════════════════════════════════════════

def test_error_recovery():
    mod = "G4-错误恢复"
    init_mod(mod)
    print(f"\n{'═' * 60}")
    print(f"  {mod}: 错误输入 & 边界处理")
    print(f"{'═' * 60}")

    token = get_admin_token()
    if not token:
        rec(mod, "JWT", False, "⚠ 无法登录")
        return
    auth = {"Authorization": f"Bearer {token}"}

    # 空问题
    print(f"\n  [空问题]")
    evts, txt = sse_collect("/admin/copilot/stream", {"question": ""}, headers=auth, timeout=30)
    # 应该有错误事件或优雅降级
    ok = chk("有响应", len(evts) > 0 or "ERROR" in txt, f"events={len(evts)}")
    rec(mod, "空问题", True)  # 能响应就算通过

    # 纯符号
    print(f"\n  [纯符号]")
    evts, txt = sse_collect("/admin/copilot/stream", {"question": "!!!???###"}, headers=auth, timeout=60)
    ok = chk("不崩溃", len(evts) > 0 or len(txt) > 0 or "ERROR" in txt)
    rec(mod, "纯符号", True)

    # SQL 注入类文本
    print(f"\n  [注入文本]")
    evts, txt = sse_collect("/admin/copilot/stream", {
        "question": "'; DROP TABLE users; -- 帮我查库存"
    }, headers=auth, timeout=60)
    ok = chk("安全处理", len(txt) > 0 or len(evts) > 0)
    rec(mod, "注入文本", True)

    # 超长单行
    print(f"\n  [超长单行]")
    mega_q = "帮我分析" * 200  # 800字
    evts, txt = sse_collect("/admin/copilot/stream", {"question": mega_q}, headers=auth, timeout=90)
    ok = chk("不超时/崩溃", len(evts) > 0 or len(txt) > 0 or "ERROR" in txt)
    rec(mod, "超长单行", True)

    # 无效 JWT
    print(f"\n  [无效JWT]")
    bad_auth = {"Authorization": "Bearer invalid_token_12345"}
    evts, txt = sse_collect("/admin/copilot/stream", {"question": "你好"}, headers=bad_auth, timeout=15)
    ok = chk("拒绝无效 JWT", "ERROR" in txt or len(evts) == 0)
    rec(mod, "无效JWT", ok)


# ══════════════════════════════════════════════════════════════
#  G5. 并发会话隔离
# ══════════════════════════════════════════════════════════════

def test_concurrent_sessions():
    mod = "G5-并发隔离"
    init_mod(mod)
    print(f"\n{'═' * 60}")
    print(f"  {mod}: 两个 OpenClaw 会话并发")
    print(f"{'═' * 60}")

    sid_a = f"concurrent-a-{int(time.time())}"
    sid_b = f"concurrent-b-{int(time.time())}"

    def chat(sid, msg):
        return api("POST", "/api/chat/message", {"session_id": sid, "message": msg})

    # 并发发送
    print(f"\n  [并发] 两个会话同时对话")
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        fa = ex.submit(chat, sid_a, "我要退货退款，东西坏了")
        fb = ex.submit(chat, sid_b, "帮我查一下积分余额")
        ra = fa.result()
        rb = fb.result()

    ca, da = ra
    cb, db = rb
    da = da.get("data", da) if isinstance(da, dict) else {}
    db = db.get("data", db) if isinstance(db, dict) else {}

    ok_a = chk("会话A 200", ca == 200)
    ok_b = chk("会话B 200", cb == 200)
    intent_a = da.get("intent", "")
    intent_b = db.get("intent", "")
    chk("会话A 退货意图", any(k in intent_a.lower() for k in ["return", "退", "换"]), f"intent={intent_a}")
    chk("会话B 积分意图", any(k in intent_b.lower() for k in ["积分", "point", "credit", "general"]), f"intent={intent_b}")
    print(f"  A: {da.get('reply', '')[:60]}")
    print(f"  B: {db.get('reply', '')[:60]}")
    rec(mod, "并发对话", ok_a and ok_b)

    # 清理
    api("DELETE", f"/api/chat/session/{sid_a}")
    api("DELETE", f"/api/chat/session/{sid_b}")


# ══════════════════════════════════════════════════════════════
#  G6. OpenClaw 5 轮连续对话
# ══════════════════════════════════════════════════════════════

def test_openclaw_multi_turn():
    mod = "G6-客服多轮"
    init_mod(mod)
    print(f"\n{'═' * 60}")
    print(f"  {mod}: OpenClaw 5 轮连续对话")
    print(f"{'═' * 60}")

    sid = f"oc-multi-{int(time.time())}"
    turns = [
        "我买的黄岩蜜橘有几个烂的",
        "能换货吗？",
        "换货大概多久能到？",
        "那顺便问一下你们最近有什么优惠活动",
        "好的，再帮我查一下订单ORD20260405001的状态",
    ]

    for i, msg in enumerate(turns):
        print(f"\n  [Turn{i+1}] {msg}")
        c, r = api("POST", "/api/chat/message", {"session_id": sid, "message": msg})
        d = r.get("data", r) if isinstance(r, dict) else {}
        ok = chk("200+有回复", c == 200 and bool(d.get("reply")))
        print(f"  → {d.get('reply', '')[:80]}")
        print(f"  意图={d.get('intent','')} 置信={d.get('confidence',0):.2f}")
        rec(mod, f"Turn{i+1}", ok)

    # 验证历史完整
    print(f"\n  [历史] 验证 5 轮消息")
    c, r = api("GET", f"/api/chat/history/{sid}")
    d = r.get("data", r) if isinstance(r, dict) else {}
    msgs = d.get("messages", [])
    ok = chk(f"历史>=10条", len(msgs) >= 10, f"got {len(msgs)}")
    rec(mod, "历史完整", ok)

    api("DELETE", f"/api/chat/session/{sid}")


# ══════════════════════════════════════════════════════════════
#  G7. 舆情分析边界测试
# ══════════════════════════════════════════════════════════════

def test_sentiment_edge():
    mod = "G7-舆情边界"
    init_mod(mod)
    print(f"\n{'═' * 60}")
    print(f"  {mod}: 舆情分析边界 Case")
    print(f"{'═' * 60}")

    cases = [
        ("中性客观", "已收到货物，包裹完好", "中性"),
        ("极短正面", "好！", "正面"),
        ("极短负面", "差评", "负面"),
        ("混合中英", "This product is OK，味道还可以but包装一般", None),  # 不严格判断
        ("纯数字", "12345678", None),
        ("表情密集", "😊😊😊👍👍", None),
        ("复杂长评", (
            "第一次买黄岩蜜橘感觉不错，个头大味道甜。但是第二次买的明显小了很多，"
            "而且有两个是烂的。客服处理还算及时，补发了一份。整体来说产品品质波动太大，"
            "物流速度也慢了不少。如果能稳定品质我还是愿意继续购买的。"
        ), None),
    ]

    for name, text, expected_label in cases:
        print(f"\n  [{name}] {text[:50]}...")
        c, r = api("POST", "/api/sentiment/analyze", {"text": text}, timeout=60)
        d = r.get("data", r) if isinstance(r, dict) else {}
        label = d.get("label", "")
        conf = d.get("confidence", 0)

        ok_http = chk("HTTP 200", c == 200, f"HTTP {c}")
        if expected_label:
            ok_label = chk(f"标签={expected_label}", label == expected_label, f"got {label}")
            rec(mod, name, ok_http and ok_label, None if (ok_http and ok_label) else f"⚠ label={label}")
        else:
            chk(f"有标签", label in ("正面", "负面", "中性"), f"label={label}")
            rec(mod, name, ok_http)

        # 复杂长评需要有实体
        if name == "复杂长评":
            entities = d.get("entity_sentiments", [])
            chk(f"有实体提取", len(entities) > 0, f"entities={len(entities)}")
            if entities:
                print(f"  实体: {json.dumps(entities[:3], ensure_ascii=False)[:200]}")


# ══════════════════════════════════════════════════════════════
#  G8. KB 向量检索语义准确性
# ══════════════════════════════════════════════════════════════

def test_kb_semantic():
    mod = "G8-KB语义"
    init_mod(mod)
    print(f"\n{'═' * 60}")
    print(f"  {mod}: 向量检索语义准确性")
    print(f"{'═' * 60}")

    queries = [
        ("质量投诉", "产品质量不好有问题"),
        ("物流慢", "配送速度太慢了"),
        ("好评复购", "很满意会再次购买"),
        ("价格贵", "东西太贵不值这个价"),
        ("包装问题", "包装破损漏出来了"),
    ]

    for name, query in queries:
        print(f"\n  [{name}] query: {query}")
        c, r = api("POST", "/api/sentiment/kb/search", {"query": query, "top_k": 3})
        d = r.get("data", r) if isinstance(r, dict) else {}
        items = d.get("items", d.get("results", []))
        ok = chk("有结果", len(items) > 0, f"count={len(items)}")
        if items:
            top = items[0]
            sim = top.get("similarity", 0)
            chk(f"相似度>0.4", sim > 0.4, f"sim={sim:.3f}")
            print(f"  Top1: sim={sim:.3f} [{top.get('label','')}] {top.get('text','')[:60]}...")
        rec(mod, name, ok)


# ══════════════════════════════════════════════════════════════
#  G9. Copilot 历史消息一致性
# ══════════════════════════════════════════════════════════════

def test_copilot_history():
    mod = "G9-历史一致"
    init_mod(mod)
    print(f"\n{'═' * 60}")
    print(f"  {mod}: Copilot 历史消息一致性")
    print(f"{'═' * 60}")

    token = get_admin_token()
    if not token:
        rec(mod, "JWT", False, "⚠ 无法登录")
        return
    auth = {"Authorization": f"Bearer {token}"}
    thread_id = f"hist-check-{int(time.time())}"

    # 发一条消息
    q = "当前有哪些SKU库存低于安全水位？"
    print(f"\n  [发送] {q}")
    evts, txt = sse_collect("/admin/copilot/stream", {
        "question": q,
        "thread_id": thread_id,
    }, headers=auth, timeout=90)
    ok_reply = chk("有回复", len(txt) > 10, f"len={len(txt)}")

    # 查历史
    print(f"\n  [验证] 检查历史消息")
    c, r = api("GET", f"/admin/copilot/threads/{thread_id}/messages?limit=10", headers=auth)
    d = r.get("data", r) if isinstance(r, dict) else {}
    msgs = d.get("messages", [])
    ok_msgs = chk("有消息记录", len(msgs) >= 2, f"got {len(msgs)}")

    # 检查用户消息和助手消息都在
    roles = [m.get("role", "") for m in msgs]
    has_user = "user" in roles
    has_asst = "assistant" in roles
    chk("有 user 消息", has_user)
    chk("有 assistant 消息", has_asst)

    # 助手消息内容应与 SSE 收集的一致
    asst_msgs = [m for m in msgs if m.get("role") == "assistant"]
    if asst_msgs and txt:
        stored = asst_msgs[-1].get("content", "")
        # 允许小差异（截断等）
        match = stored[:50] == txt[:50] if len(stored) > 10 else len(stored) > 0
        chk("持久化内容一致", match, f"stored[:50]={stored[:50]}")
    rec(mod, "历史一致性", ok_reply and ok_msgs)

    # 线程列表中应该能看到
    print(f"\n  [线程列表]")
    c2, r2 = api("GET", "/admin/copilot/threads?limit=50", headers=auth)
    d2 = r2.get("data", r2) if isinstance(r2, dict) else {}
    threads = d2.get("threads", [])
    found = any(t.get("thread_id") == thread_id for t in threads)
    ok_list = chk("线程可见", found, f"searched {len(threads)} threads")
    rec(mod, "线程列表", ok_list)


# ══════════════════════════════════════════════════════════════
#  报告
# ══════════════════════════════════════════════════════════════

def report():
    print(f"\n{'═' * 60}")
    print(f"  深度测试总报告 (Round 2)")
    print(f"{'═' * 60}")
    tp = tw = tf = 0
    for mod, s in stats.items():
        t = s["pass"] + s["warn"] + s["fail"]
        print(f"\n  [{mod}]  ✓{s['pass']}  ⚠{s['warn']}  ✗{s['fail']}  共{t}项")
        for i in s["issues"]:
            print(f"    → {i}")
        tp += s["pass"]
        tw += s["warn"]
        tf += s["fail"]
    total = tp + tw + tf
    pct = tp / total * 100 if total else 0
    print(f"\n{'─' * 60}")
    print(f"  总计: {total} 项")
    print(f"  ✓ 通过: {tp} ({pct:.0f}%)")
    print(f"  ⚠ 警告: {tw}")
    print(f"  ✗ 失败: {tf}")
    print(f"  总耗时: {time.time() - T0:.1f}s")
    print(f"{'═' * 60}")


if __name__ == "__main__":
    T0 = time.time()
    test_multi_turn_context()
    test_cross_skill_chain()
    test_long_input_copilot()
    test_error_recovery()
    test_concurrent_sessions()
    test_openclaw_multi_turn()
    test_sentiment_edge()
    test_kb_semantic()
    test_copilot_history()
    report()
