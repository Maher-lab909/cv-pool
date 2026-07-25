import json
from pathlib import Path

profiles, failed = [], []
for f in sorted(Path("profiles").glob("*.json")):
    try:
        profiles.append(json.loads(f.read_text(encoding="utf-8")))
    except Exception:
        failed.append(f.name)

out = Path("all_profiles.json")
out.write_text(json.dumps(profiles, ensure_ascii=False), encoding="utf-8")

print(f"merged {len(profiles)} profiles -> {out}")
if failed:
    print(f"skipped {len(failed)} bad files: {failed}")