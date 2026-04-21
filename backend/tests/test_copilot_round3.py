"""Round 3-6: Copilot deep integration tests"""
import requests, json, time, sys

BASE = "http://127.0.0.1:8000"
BIZ = BASE + "/api/copilot/stream"
OPS = BASE + "/admin/copilot/stream"

def login():
    r = requests.post(BASE + "/admin/auth/login", json={"username": "admin", "password": "admin"})
    return r.json()["access_token"]

TOKEN = login()
H = {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"}

def stream_ask(url, body):
    resp = requests.post(url, headers=H, json=body, stream=True, timeout=90)
    text, tid, skill, err = [], "", "", []
    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "): continue
        raw = line[6:].strip()
        if raw == "[DONE]": continue
        try:
            e = json.loads(raw)
            t = e.get("type", "")
            if t == "text_delta": text.append(e.get("content", ""))
            elif t == "run_start": tid = e.get("metadata", {}).get("thread_id", "") or tid
            elif t == "tool_call_start": skill = e.get("metadata", {}).get("display_name", "") or e.get("metadata", {}).get("skill", "")
            elif t == "run_error": err.append(e.get("content", ""))
        except: pass
    return {"status": resp.status_code, "text": "".join(text), "tid": tid, "skill": skill, "err": "".join(err)}

def biz(q, tid=None):
    body = {"question": q}
    if tid: body["thread_id"] = tid
    return stream_ask(BIZ, body)

def ops(q, tid=None):
    body = {"question": q, "mode": "ops"}
    if tid: body["thread_id"] = tid
    return stream_ask(OPS, body)

SEP = "=" * 60
results = []

def check(name, condition, detail=""):
    tag = "PASS" if condition else "FAIL"
    results.append((name, tag))
    print("  [%s] %s %s" % (tag, name, ("| " + detail[:80]) if detail else ""))

# ── ROUND 3: Edge Cases ──
print("\nROUND 3: EDGE CASES")
print(SEP)

# 3a: Auth checks (DEV_BACKDOOR_ENABLED=true allows no-auth in dev)
r = requests.post(BIZ, json={"question": "test"})
check("3a no-auth", r.status_code in (200, 401, 403), "status=%d (200=dev_backdoor)" % r.status_code)

r = requests.post(BIZ, headers={"Authorization": "Bearer invalid", "Content-Type": "application/json"}, json={"question": "test"})
check("3b bad-token", r.status_code in (401, 403), "status=%d" % r.status_code)

r = requests.post(BIZ, headers=H, json={"wrong_field": "test"})
check("3c missing-question", r.status_code == 422, "status=%d" % r.status_code)

# 3d: Whitespace
res = biz("   ")
check("3d whitespace-input", res["status"] == 200 and len(res["text"]) > 0, "%dch" % len(res["text"]))

# 3e: XSS
res = biz('<script>alert("xss")</script>')
check("3e xss-safe", res["status"] == 200 and "<script>" not in res["text"], "%dch" % len(res["text"]))

# 3f: SQL injection
res = biz("'; DROP TABLE users; --")
check("3f sqli-safe", res["status"] == 200 and len(res["text"]) > 0, "%dch" % len(res["text"]))

# 3g: Emoji
res = biz("客户分析 \U0001f680\U0001f4ca")
check("3g emoji", res["status"] == 200 and len(res["text"]) > 0, "%dch skill=%s" % (len(res["text"]), res["skill"]))

# 3h: Fake thread_id
res = stream_ask(BIZ, {"question": "hello", "thread_id": "nonexistent-fake-thread"})
check("3h fake-thread", res["status"] == 200 and len(res["text"]) > 0, "%dch" % len(res["text"]))

# ── ROUND 4: Feedback + Suggestions ──
print("\nROUND 4: FEEDBACK & SUGGESTIONS")
print(SEP)

# Get a thread with messages
r = requests.get(BASE + "/api/copilot/threads", headers=H)
threads = r.json().get("data", {}).get("threads", [])
check("4a list-threads", len(threads) > 0, "%d threads" % len(threads))

if threads:
    tid = threads[0]["id"]
    r = requests.get(BASE + "/api/copilot/threads/%s/messages?limit=5" % tid, headers=H)
    msgs = r.json().get("data", {}).get("messages", [])
    check("4b load-messages", len(msgs) > 0, "%d messages" % len(msgs))

    asst = [m for m in msgs if m.get("role") == "assistant"]
    if asst:
        mid = asst[0]["id"]
        # Thumbs up
        r = requests.post(BASE + "/api/copilot/feedback", headers=H, json={"message_id": mid, "feedback": 1, "feedback_text": "test"})
        check("4c feedback-up", r.status_code == 200, r.text[:60])

        # Thumbs down
        r = requests.post(BASE + "/api/copilot/feedback", headers=H, json={"message_id": mid, "feedback": -1, "feedback_text": "not helpful"})
        check("4d feedback-down", r.status_code == 200, r.text[:60])

        # Verify feedback persisted
        r = requests.get(BASE + "/api/copilot/threads/%s/messages?limit=5" % tid, headers=H)
        msgs2 = r.json().get("data", {}).get("messages", [])
        updated = [m for m in msgs2 if m.get("id") == mid]
        if updated:
            check("4e feedback-persist", updated[0].get("feedback") == -1, "feedback=%s" % updated[0].get("feedback"))
        else:
            check("4e feedback-persist", False, "message not found")
    else:
        check("4c-e feedback", False, "no assistant messages")

# ── ROUND 5: Thinking + Skill routing accuracy ──
print("\nROUND 5: SKILL ROUTING ACCURACY")
print(SEP)

routing_tests = [
    ("biz", "帮我预测下周的销售额", "预测", "销售预测"),
    ("biz", "哪些商品需要补货？", "库存", "库存优化"),
    ("biz", "分析客户消费行为变化", "客户", "客户洞察"),
    ("biz", "最近的客户评价情绪怎样？", "舆情", "舆情"),
    ("biz", "哪些商品经常搭配购买？", "关联", "关联"),
    ("ops", "系统各服务运行状态", "系统", "系统"),
    ("ops", "最近有失败的trace吗？", "Trace", "Trace"),
    ("ops", "检测异常交易", "欺诈", "欺诈"),
]

for mode, q, expected_kw, label in routing_tests:
    fn = ops if mode == "ops" else biz
    res = fn(q)
    skill_lower = res["skill"].lower()
    matched = expected_kw.lower() in skill_lower or expected_kw in res["skill"]
    check("5 %s->%s" % (label, expected_kw), matched and len(res["text"]) > 50,
          "got=%s %dch" % (res["skill"] or "general", len(res["text"])))
    time.sleep(0.3)

# ── ROUND 6: Multi-turn with topic switch ──
print("\nROUND 6: TOPIC SWITCH IN MULTI-TURN")
print(SEP)

res1 = biz("分析客户流失风险")
tid = res1["tid"]
check("6a start-customer", "客户" in res1["skill"], res1["skill"])
time.sleep(0.5)

res2 = biz("那库存情况呢？有需要补货的吗？", tid)
check("6b switch-to-inventory", "库存" in res2["skill"] or "inventory" in res2["skill"].lower(),
      "got=%s" % (res2["skill"] or "general"))
time.sleep(0.5)

res3 = biz("再看看舆情", tid)
check("6c switch-to-sentiment", "舆情" in res3["skill"] or "sentiment" in res3["skill"].lower(),
      "got=%s" % (res3["skill"] or "general"))

# ── Summary ──
print("\n" + SEP)
passed = sum(1 for _, t in results if t == "PASS")
failed = sum(1 for _, t in results if t == "FAIL")
print("TOTAL: %d PASS / %d FAIL / %d tests" % (passed, failed, len(results)))
if failed:
    print("\nFailed tests:")
    for name, tag in results:
        if tag == "FAIL":
            print("  - %s" % name)
