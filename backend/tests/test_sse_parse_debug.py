"""Debug SSE parse exactly as test_full_v2 does"""
import requests, json, urllib.request

BASE = "http://127.0.0.1:8000"
token = requests.post(BASE + "/admin/auth/login", json={"username": "admin", "password": "admin"}).json()["access_token"]

url = BASE + "/admin/copilot/stream"
body = json.dumps({"question": "你好"}).encode()
req = urllib.request.Request(url, data=body, method="POST")
req.add_header("Content-Type", "application/json")
req.add_header("Authorization", "Bearer " + token)

resp = urllib.request.urlopen(req, timeout=60)
raw_body = resp.read().decode("utf-8", errors="replace")

print("raw len:", len(raw_body))
print("has \\r\\n:", "\\r\\n" in repr(raw_body[:200]))
print("first 200 repr:", repr(raw_body[:200]))

# Exact same parse as test_full_v2
frames = raw_body.split("\n\n")
print("\nframes:", len(frames))

events = []
full_text = ""
for frame in frames:
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
        except Exception as ex:
            pd2 = {"raw": ed, "parse_error": str(ex)}
        if not et and "type" in pd2:
            et = pd2["type"]
        if et:
            events.append({"type": et})
            if et in ("text_delta", "token"):
                full_text += pd2.get("content", "")

print("events:", len(events))
print("types:", set(e["type"] for e in events))
print("text len:", len(full_text))
print("text:", full_text[:100])
