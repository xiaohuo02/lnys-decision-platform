"""Debug: compare urllib vs requests for SSE"""
import requests, json, urllib.request

BASE = "http://127.0.0.1:8000"

# Login
token = requests.post(BASE + "/admin/auth/login", json={"username": "admin", "password": "admin"}).json()["access_token"]

# Test 1: urllib (same method as test_full_v2.py)
print("=== urllib.request ===")
url = BASE + "/admin/copilot/stream"
body = json.dumps({"question": "系统状态"}).encode()
req = urllib.request.Request(url, data=body, method="POST")
req.add_header("Content-Type", "application/json")
req.add_header("Authorization", "Bearer " + token)
try:
    resp = urllib.request.urlopen(req, timeout=60)
    raw = resp.read().decode("utf-8", errors="replace")
    print("len=%d" % len(raw))
    print("first 500:", raw[:500])
except urllib.error.HTTPError as e:
    print("HTTP ERROR %d" % e.code)
    print(e.read().decode()[:200])
except Exception as e:
    print("ERROR:", e)

# Test 2: requests streaming
print("\n=== requests streaming ===")
H = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
resp2 = requests.post(url, headers=H, json={"question": "系统状态"}, stream=True, timeout=60)
print("status:", resp2.status_code)
text = []
for line in resp2.iter_lines(decode_unicode=True):
    if not line or not line.startswith("data: "): continue
    raw = line[6:].strip()
    if raw == "[DONE]": continue
    try:
        e = json.loads(raw)
        if e.get("type") == "text_delta":
            text.append(e.get("content", ""))
    except: pass
print("text len=%d" % len("".join(text)))
print("snippet:", "".join(text)[:200])

# Test 3: BIZ endpoint with urllib
print("\n=== BIZ urllib ===")
url2 = BASE + "/api/copilot/stream"
body2 = json.dumps({"question": "最近销售趋势怎么样？"}).encode()
req2 = urllib.request.Request(url2, data=body2, method="POST")
req2.add_header("Content-Type", "application/json")
req2.add_header("Authorization", "Bearer " + token)
try:
    resp3 = urllib.request.urlopen(req2, timeout=60)
    raw3 = resp3.read().decode("utf-8", errors="replace")
    print("len=%d" % len(raw3))
    print("first 500:", raw3[:500])
except urllib.error.HTTPError as e:
    print("HTTP ERROR %d" % e.code)
    print(e.read().decode()[:200])
except Exception as e:
    print("ERROR:", e)
