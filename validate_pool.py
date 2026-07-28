"""
Layer 3 v0.1 — validate the whole pool against the Pydantic mirror.

Reports how many stored profiles are schema-valid, and lists every violation
with its exact location and reason. This is the baseline 'trust' number, and the
same validation that will guard future profiling runs (Layer 3 v0.2).
"""

import sys
import json
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE / "schema"))
from models import Profile                    # noqa: E402
from pydantic import ValidationError          # noqa: E402

PROFILES = BASE / "profiles"
files = sorted(PROFILES.glob("*.json"))

valid = 0
failures = []
for pf in files:
    data = json.loads(pf.read_text(encoding="utf-8"))
    prof = data.get("profile", data)          # stored as {_meta, profile}
    try:
        Profile.model_validate(prof)
        valid += 1
    except ValidationError as e:
        reasons = [f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()]
        failures.append((pf.name, reasons))

n = len(files) or 1
print("=" * 66)
print("LAYER 3 v0.1 — POOL VALIDATION (Pydantic mirror, v2.1 schema)")
print(f"  profiles checked : {len(files)}")
print(f"  schema-valid     : {valid}  ({valid / n * 100:.1f}%)")
print(f"  with violations  : {len(files) - valid}")
print("-" * 66)
if failures:
    print("VIOLATIONS (file -> field -> reason):")
    for name, reasons in failures:
        print(f"  {name}")
        for r in reasons:
            print(f"       {r}")
else:
    print("No violations — every profile validates against the schema. ✅")
print("=" * 66)
