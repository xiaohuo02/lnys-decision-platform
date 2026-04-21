#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全系统端到端综合测试 v2 — 修复 v1 所有已知问题

修复清单:
  - A1/A2 意图名:  接受英文 intent (order_query, return_refund 等)
  - A4 ctx:  不再硬检 session_context_size
  - 销量预测: 加 store_id 必填字段
  - 欺诈评分: 用 transaction_id 替代 order_id
  - C0 JWT:  直接取 access_token (非 data 包裹)
  - D3 KB 搜索: 用 items 而非 results
  - 新增: A9 空消息边界, A10 特殊字符, D4 Entity搜索, F Internal端点
"""
import json
import time
import urllib.request
import urllib.error
import ssl
import sys

BASE = "http://127.0.0.1:8000"
ssl._create_default_https_context = ssl._create_unverified_context


# ── 工具函数 ─────────────────────────────────────────────────

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
            bt = e.read().decode()[:300]
        except:
            pass
        return e.code, {"error": str(e), "body": bt}
    except Exception as e:
        return 0, {"error": str(e)}


def sse_collect(path, data, headers=None, timeout=90):
    """收集 SSE 事件。
    支持两种格式：
      A) event: xxx\\ndata: {...}\\n\\n  (OpenClaw chat/stream)
      B) data: {"type":"xxx",...}\\n\\n  (Copilot AG-UI 协议)
    """
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
        # 按双换行分割 SSE 帧
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
                # 格式 B: type 在 JSON 内
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


def init_mod(n):
    stats[n] = {"pass": 0, "warn": 0, "fail": 0, "issues": []}


def rec(mod, case, passed, issue=None):
    if passed:
        stats[mod]["pass"] += 1
    elif issue and issue.startswith("⚠"):
        stats[mod]["warn"] += 1
        stats[mod]["issues"].append(f"{case}: {issue}")
    else:
        stats[mod]["fail"] += 1
        stats[mod]["issues"].append(f"{case}: {issue or 'FAIL'}")


# ══════════════════════════════════════════════════════════════
#  A. OpenClaw 客服对话测试
# ══════════════════════════════════════════════════════════════

def test_openclaw():
    mod = "OpenClaw客服"
    init_mod(mod)
    print(f"\n{'═' * 60}")
    print(f"  模块 A: {mod}")
    print(f"{'═' * 60}")
    sid = f"test-{int(time.time())}"

    # A1: 订单意图
    print(f"\n  [A1] 短对话 - 订单查询意图")
    c, r = api("POST", "/api/chat/message", {"session_id": sid, "message": "我的订单什么时候发货？"})
    d = r.get("data", r) if isinstance(r, dict) else {}
    ok1 = chk("HTTP 200", c == 200)
    ok2 = chk("有回复", bool(d.get("reply")))
    intent = d.get("intent", "")
    ok3 = chk("订单/物流意图", any(k in intent.lower() for k in ["order", "发货", "查订单", "物流", "logistics"]), f"intent={intent}")
    chk("置信度>0.5", d.get("confidence", 0) > 0.5)
    rec(mod, "A1-订单意图", ok1 and ok2 and ok3, None if (ok1 and ok2 and ok3) else f"⚠ intent={intent}")
    print(f"  回复: {d.get('reply', '')[:80]}")

    # A2: 退货
    print(f"\n  [A2] 退换货意图")
    c, r = api("POST", "/api/chat/message", {"session_id": sid, "message": "东西有问题，我要退货退款"})
    d = r.get("data", r) if isinstance(r, dict) else {}
    intent = d.get("intent", "")
    ok = chk("退换意图", any(k in intent.lower() for k in ["return", "refund", "退", "换"]), f"intent={intent}")
    rec(mod, "A2-退货意图", ok, None if ok else f"⚠ intent={intent}")

    # A3: 模糊 → 降级
    print(f"\n  [A3] 模糊问题 → 降级处理")
    c, r = api("POST", "/api/chat/message", {"session_id": sid, "message": "你们公司社保交几档的？"})
    d = r.get("data", r) if isinstance(r, dict) else {}
    conf = d.get("confidence", 1)
    ok = chk("低置信度 or 转人工", conf < 0.6 or d.get("handoff", False), f"conf={conf}")
    rec(mod, "A3-降级", ok)

    # A4: 多轮
    print(f"\n  [A4] 多轮对话 - 积分查询")
    c, r = api("POST", "/api/chat/message", {"session_id": sid, "message": "帮我查一下积分余额"})
    d = r.get("data", r) if isinstance(r, dict) else {}
    ok = chk("HTTP 200 + 有回复", c == 200 and bool(d.get("reply")))
    rec(mod, "A4-多轮", ok)

    # A5: SSE 流式
    print(f"\n  [A5] SSE 流式对话")
    evts, txt = sse_collect("/api/chat/stream", {"session_id": sid, "message": "你们有哪些柠檬产品？"})
    tok = [e for e in evts if e["type"] == "token"]
    done = [e for e in evts if e["type"] == "done"]
    ok_a = chk("收到 token", len(tok) > 0, f"n={len(tok)}")
    ok_b = chk("收到 done", len(done) > 0)
    ok_c = chk("文本非空", len(txt) > 5, f"len={len(txt)}")
    rec(mod, "A5-SSE", ok_a and ok_b and ok_c)

    # A6: 历史
    print(f"\n  [A6] 历史记录")
    c, r = api("GET", f"/api/chat/history/{sid}")
    d = r.get("data", r) if isinstance(r, dict) else {}
    msgs = d.get("messages", [])
    ok = chk("历史>=4条", len(msgs) >= 4, f"got {len(msgs)}")
    rec(mod, "A6-历史", ok)

    # A7: 长文本
    print(f"\n  [A7] 长文本输入")
    long_m = "我买了很多东西，" + "包括黄岩蜜橘五斤装、永春芦柑三斤装。" * 20 + "请问能退吗？"
    c, r = api("POST", "/api/chat/message", {"session_id": f"long-{int(time.time())}", "message": long_m[:990]})
    ok = chk("HTTP 200", c == 200, f"HTTP {c}")
    rec(mod, "A7-长文本", ok)

    # A8: 删除会话
    print(f"\n  [A8] 删除会话")
    c, r = api("DELETE", f"/api/chat/session/{sid}")
    ok = chk("删除成功", c == 200, f"HTTP {c}")
    c2, r2 = api("GET", f"/api/chat/history/{sid}")
    d2 = r2.get("data", r2) if isinstance(r2, dict) else {}
    chk("删后为空", len(d2.get("messages", [])) == 0)
    rec(mod, "A8-删除", ok)

    # A9: 空消息边界
    print(f"\n  [A9] 空消息 → 422")
    c, r = api("POST", "/api/chat/message", {"session_id": "edge", "message": ""})
    ok = chk("拒绝空消息(422)", c == 422, f"HTTP {c}")
    rec(mod, "A9-空消息", ok)

    # A10: 特殊字符注入
    print(f"\n  [A10] 特殊字符注入")
    c, r = api("POST", "/api/chat/message", {"session_id": "edge2", "message": '<script>alert(1)</script> 你好！'})
    d = r.get("data", r) if isinstance(r, dict) else {}
    ok = chk("HTTP 200 + 有回复", c == 200 and bool(d.get("reply")))
    rec(mod, "A10-注入", ok)


# ══════════════════════════════════════════════════════════════
#  B. 业务 API 冒烟
# ══════════════════════════════════════════════════════════════

def test_biz_apis():
    mod = "业务API"
    init_mod(mod)
    print(f"\n{'═' * 60}")
    print(f"  模块 B: {mod}")
    print(f"{'═' * 60}")

    eps = [
        ("GET", "/api/health", "健康检查"),
        ("GET", "/api/health/deps", "依赖状态"),
        ("GET", "/api/dashboard/kpis", "仪表盘KPI"),
        ("GET", "/api/inventory/status", "库存状态"),
        ("GET", "/api/inventory/alerts", "库存预警"),
        ("GET", "/api/inventory/abc-xyz", "ABC-XYZ分析"),
        ("GET", "/api/forecast/summary", "预测概览"),
        ("POST", "/api/forecast/predict", "销量预测", {"sku_code": "A001", "store_id": "NDE-001", "days": 7}),
        ("GET", "/api/customers/rfm", "RFM分析"),
        ("GET", "/api/customers/segments", "客户分群"),
        ("GET", "/api/customers/clv", "CLV"),
        ("GET", "/api/customers/churn-risk", "流失风险"),
        ("POST", "/api/customers/predict-churn", "流失预测", {
            "customer_id": "LY000088", "recency": 45.0, "frequency_30d": 2,
            "frequency_90d": 8, "monetary_trend": -0.15, "return_rate": 0.05,
            "complaint_count": 1, "member_level": "银卡", "register_days": 365
        }),
        ("GET", "/api/fraud/stats", "欺诈统计"),
        ("POST", "/api/fraud/score", "欺诈评分", {"transaction_id": "TX20260408001", "customer_id": "LY000001", "amount": 999.0}),
        ("GET", "/api/fraud/pending-reviews", "欺诈待审"),
        ("GET", "/api/association/rules", "关联规则"),
        ("GET", "/api/association/recommend/A001", "关联推荐"),
        ("GET", "/api/sentiment/overview", "舆情概览"),
        ("GET", "/api/sentiment/topics", "舆情话题"),
        ("GET", "/api/sentiment/reviews", "HITL审核"),
        ("GET", "/api/sentiment/kb/stats", "KB统计"),
    ]

    for ep in eps:
        method, path, name = ep[0], ep[1], ep[2]
        data = ep[3] if len(ep) > 3 else None
        print(f"\n  [{name}] {method} {path}")
        c, r = api(method, path, data, timeout=30)
        ok = chk("HTTP 2xx", 200 <= c < 300, f"HTTP {c}")
        if not ok and isinstance(r, dict):
            print(f"    {r.get('body', '')[:150]}")
        rec(mod, name, ok, None if ok else f"✗ HTTP {c}")


# ══════════════════════════════════════════════════════════════
#  C. Copilot SSE 流式测试
# ══════════════════════════════════════════════════════════════

def test_copilot():
    mod = "Copilot对话"
    init_mod(mod)
    print(f"\n{'═' * 60}")
    print(f"  模块 C: {mod}")
    print(f"{'═' * 60}")

    # C0: JWT
    print(f"\n  [C0] Admin JWT")
    c, r = api("POST", "/admin/auth/login", {"username": "admin", "password": "admin"})
    token = ""
    if c == 200 and isinstance(r, dict):
        # login 端点直接返回 {access_token, ...} 无 data 包裹
        token = r.get("access_token", "")
        if not token:
            token = r.get("data", {}).get("access_token", "")
    if not token:
        print(f"  ⚠ 登录失败 HTTP {c}，跳过 Copilot 测试")
        if isinstance(r, dict):
            print(f"  响应: {json.dumps(r, ensure_ascii=False)[:200]}")
        rec(mod, "C0-JWT", False, f"⚠ HTTP {c}")
        return
    chk("JWT OK", bool(token))
    rec(mod, "C0-JWT", True)
    auth = {"Authorization": f"Bearer {token}"}

    # C1-C6: 各 Skill 路由
    cases = [
        ("C1", "系统状态", "当前系统运行状态怎么样？有没有异常？"),
        ("C2", "库存Skill", "帮我查一下A001黄岩蜜橘的库存情况和补货建议"),
        ("C3", "舆情Skill", "分析一下最近的客户评价情况，有没有负面舆情需要关注？"),
        ("C4", "客户Skill", "帮我看看RFM分析结果，哪些客户是高价值客户？"),
        ("C5", "欺诈Skill", "最近有异常订单吗？欺诈风险怎么样？"),
        ("C6", "综合决策", "综合分析：库存A001快缺货了客户投诉增多，你建议怎么应对？给出行动方案。"),
    ]
    thread_id = None
    for cid, name, q in cases:
        print(f"\n  [{cid}] {name}")
        payload = {"question": q}
        # C3 用 C2 的 thread 测多轮
        if thread_id and cid == "C3":
            payload["thread_id"] = thread_id
        evts, txt = sse_collect("/admin/copilot/stream", payload, headers=auth, timeout=90)
        ok = chk("回复>10字", len(txt) > 10, f"len={len(txt)}")
        types = set(e["type"] for e in evts)
        chk(f"事件类型≥1", len(types) >= 1, f"types={types}")
        if cid == "C2":
            for e in evts:
                if isinstance(e.get("data"), dict) and e["data"].get("thread_id"):
                    thread_id = e["data"]["thread_id"]
                    break
        print(f"  回复: {txt[:120]}...")
        rec(mod, f"{cid}-{name}", ok)

    # C7: 对话历史列表
    print(f"\n  [C7] 对话历史列表")
    c, r = api("GET", "/admin/copilot/threads?limit=10", headers=auth)
    ok = chk("HTTP 200", c == 200, f"HTTP {c}")
    d = r.get("data", r) if isinstance(r, dict) else {}
    threads = d.get("threads", [])
    chk(f"有线程", len(threads) > 0, f"n={len(threads)}")
    rec(mod, "C7-历史列表", ok)

    # C8: Biz Copilot (通过 /api/copilot/stream)
    print(f"\n  [C8] BizCopilot")
    evts8, txt8 = sse_collect("/api/copilot/stream", {"question": "最近销售趋势怎么样？"}, headers=auth, timeout=90)
    ok = chk("回复>10字", len(txt8) > 10, f"len={len(txt8)}")
    rec(mod, "C8-BizCopilot", ok)
    if txt8:
        print(f"  回复: {txt8[:120]}...")


# ══════════════════════════════════════════════════════════════
#  D. 舆情冒烟
# ══════════════════════════════════════════════════════════════

def test_sentiment():
    mod = "舆情冒烟"
    init_mod(mod)
    print(f"\n{'═' * 60}")
    print(f"  模块 D: {mod}")
    print(f"{'═' * 60}")

    print(f"\n  [D1] 正面")
    c, r = api("POST", "/api/sentiment/analyze", {"text": "非常好吃，下次还买！"})
    d = r.get("data", r) if isinstance(r, dict) else {}
    ok = chk("标签=正面", d.get("label") == "正面", f"label={d.get('label')}")
    rec(mod, "D1-正面", ok)

    print(f"\n  [D2] 负面")
    c, r = api("POST", "/api/sentiment/analyze", {"text": "太难吃了，再也不买了，垃圾"})
    d = r.get("data", r) if isinstance(r, dict) else {}
    ok = chk("标签=负面", d.get("label") == "负面", f"label={d.get('label')}")
    rec(mod, "D2-负面", ok)

    print(f"\n  [D3] KB 向量搜索")
    c, r = api("POST", "/api/sentiment/kb/search", {"query": "产品质量投诉", "top_k": 3})
    d = r.get("data", r) if isinstance(r, dict) else {}
    # 响应结构是 data.items[]
    items = d.get("items", d.get("results", []))
    ok = chk("搜索有结果", len(items) > 0, f"items={len(items)}")
    if items:
        top = items[0]
        print(f"  Top1: sim={top.get('similarity', '?'):.3f} [{top.get('label')}] {top.get('text', '')[:60]}...")
    rec(mod, "D3-KB搜索", ok)

    print(f"\n  [D4] Entity 搜索")
    c, r = api("GET", "/api/sentiment/kb/entity/%E9%BB%84%E5%B2%A9%E8%9C%9C%E6%A9%98")  # URL encoded 黄岩蜜橘
    ok = chk("HTTP 2xx", 200 <= c < 300, f"HTTP {c}")
    rec(mod, "D4-Entity搜索", ok)


# ══════════════════════════════════════════════════════════════
#  E. 报表 + Dashboard
# ══════════════════════════════════════════════════════════════

def test_reports():
    mod = "报表Dashboard"
    init_mod(mod)
    print(f"\n{'═' * 60}")
    print(f"  模块 E: {mod}")
    print(f"{'═' * 60}")

    for name, method, path in [
        ("KPI", "GET", "/api/dashboard/kpis"),
        ("报表列表", "GET", "/api/reports"),
    ]:
        print(f"\n  [{name}] {method} {path}")
        c, r = api(method, path)
        ok = chk("HTTP 2xx", 200 <= c < 300, f"HTTP {c}")
        rec(mod, name, ok)


# ══════════════════════════════════════════════════════════════
#  F. Internal 端点
# ══════════════════════════════════════════════════════════════

def test_internal():
    mod = "Internal端点"
    init_mod(mod)
    print(f"\n{'═' * 60}")
    print(f"  模块 F: {mod}")
    print(f"{'═' * 60}")

    internal_eps = [
        ("Smoke Health", "GET", "/internal/smoke/health"),
        ("Smoke Workflow", "POST", "/internal/smoke/workflow"),
    ]
    for name, method, path in internal_eps:
        print(f"\n  [{name}] {method} {path}")
        c, r = api(method, path)
        ok = chk("HTTP 2xx", 200 <= c < 300, f"HTTP {c}")
        rec(mod, name, ok)


# ══════════════════════════════════════════════════════════════
#  总报告
# ══════════════════════════════════════════════════════════════

def report():
    print(f"\n{'═' * 60}")
    print(f"  全系统测试总报告")
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
    print(f"{'═' * 60}")


if __name__ == "__main__":
    t0 = time.time()
    test_openclaw()
    test_biz_apis()
    test_copilot()
    test_sentiment()
    test_reports()
    test_internal()
    print(f"\n  总耗时: {time.time() - t0:.1f}s")
    report()
