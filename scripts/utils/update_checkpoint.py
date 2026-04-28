# -*- coding: utf-8 -*-
import json
from pathlib import Path

cp = Path("checkpoints/progress.json")
data = json.loads(cp.read_text(encoding="utf-8"))

for task in data["tasks"]:
    tid = str(task.get("id", ""))
    if tid in ("16", "18"):
        task["status"] = "done"
        task["exit_code"] = 0

cp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
done = sum(1 for t in data["tasks"] if t.get("status") == "done")
total = len(data["tasks"])
print(f"checkpoint updated: {done}/{total} done")
for t in data["tasks"]:
    print(f"  [{t.get('status','?'):6}] {t.get('id','?'):>2}  {t.get('name','')}")
