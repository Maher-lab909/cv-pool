"""
The Pool — one-off repair (v2.1, $0, offline)

Fixes three known data issues in the 400 profiles, in place:
  1. UNWRAP competencies stored as a JSON string or a dict -> plain list
     (the 24-job / 111-tag double-encoding bug).
  2. industry "marketing" -> "media_entertainment" (a job_family value that
     leaked into the industry field on 3 marketing-agency jobs).
  3. DROP 2 confirmed non-CV records (a company profile and a portfolio).
     The other zero-job profiles are real people and are kept.

Operates on the canonical store (profiles/*.json) + the ledger, then rebuilds
all_profiles.json so the combined export stays in sync. No API calls.
"""

import csv
import json
from pathlib import Path

BASE = Path(__file__).parent
PROFILES = BASE / "profiles"
EXTRACTED = BASE / "extracted"
LEDGER = BASE / "profiles_ledger.csv"
COMBINED = BASE / "all_profiles.json"

# Exactly two confirmed non-CVs (verified by source_file).
JUNK = {
    "linkedin__2025 mar - 2025 dec__boud plus 2026.txt",              # company profile
    "linkedin__2026 jan - 2026 jul__portfolio.alanoud albasri9.txt",  # a portfolio
}


def normalize_comps(raw):
    """Unwrap competencies whether stored as a JSON string, a dict, or already
    a list. Leaves a proper list (plain tags OR {id,scope}) untouched."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return []
    if isinstance(raw, dict):
        raw = raw.get("competencies", [])
    return raw if isinstance(raw, list) else []


unwrapped_jobs = tags_recovered = industry_fixed = 0
dropped = []
scanned = 0

for pf in sorted(PROFILES.glob("*.json")):
    data = json.loads(pf.read_text(encoding="utf-8"))
    sf = data.get("_meta", {}).get("source_file", "")

    # 3. drop junk: remove profile + its extracted text
    if sf in JUNK:
        pf.unlink()
        (EXTRACTED / sf).unlink(missing_ok=True)
        dropped.append(sf)
        continue

    changed = False
    for job in data.get("profile", {}).get("experience", []):
        # 1. unwrap
        c = job.get("competencies")
        if isinstance(c, (str, dict)):
            fixed = normalize_comps(c)
            job["competencies"] = fixed
            unwrapped_jobs += 1
            tags_recovered += len(fixed)
            changed = True
        # 2. industry
        if job.get("industry") == "marketing":
            job["industry"] = "media_entertainment"
            industry_fixed += 1
            changed = True

    if changed:
        pf.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    scanned += 1

# clean the ledger
if LEDGER.exists() and dropped:
    rows = list(csv.DictReader(LEDGER.open(encoding="utf-8-sig")))
    kept = [r for r in rows if r["source_file"] not in JUNK]
    with LEDGER.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(kept)

# rebuild the combined export from the (now repaired) canonical store
profiles = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(PROFILES.glob("*.json"))]
COMBINED.write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")

print("=" * 56)
print("REPAIR DONE")
print(f"  profiles scanned        : {scanned}")
print(f"  jobs unwrapped          : {unwrapped_jobs}  ({tags_recovered} tags recovered)")
print(f"  industry marketing fixed: {industry_fixed}")
print(f"  junk records dropped    : {len(dropped)}")
for d in dropped:
    print(f"      - {d}")
print(f"  pool now                : {len(profiles)} profiles")
print("=" * 56)
print("NOTE: the 2 junk raw files still sit in raw/linkedin/ (harmless — they")
print("won't re-profile). Delete them by hand if you want raw/ clean too.")
