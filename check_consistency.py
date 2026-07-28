"""
Layer 3 v0.2 — consistency check: computed years vs claimed seniority.

No API, no answer key — pure Python over the stored profiles. For each person:
compute actual months worked from their job dates (merge overlaps, ignore gaps),
then compare against the seniority label the model assigned. Flag contradictions.

The schema's seniority menu mixes two measuring sticks:
  TENURE-based : junior 0-2 yrs · mid 2-5 · senior 5+ (individual contributor)
  ROLE-based   : lead / manager / director / executive — defined by the role
                 held, with NO year requirement at all.

So the report splits accordingly:
  HARD violations — tenure labels breaking their own definitions
                    (junior with 12 yrs is wrong by definition).
  SOFT flags      — role labels with unusually thin tenure (manager at 2.8
                    yrs is LEGAL by the schema; just worth a human glance).
"""

import sys
import json
from pathlib import Path
from datetime import date

BASE = Path(__file__).parent
PROFILES = BASE / "profiles"

SLACK = 1.0  # years of tolerance before something counts as a contradiction


def parse_ym(value):
    if not value:
        return None
    parts = str(value).split("-")
    try:
        return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 1)
    except (ValueError, IndexError):
        return None


def compute_years(experience):
    """Actual months worked: per-job spans, merged overlaps, gaps ignored."""
    today = (date.today().year, date.today().month)
    spans = []
    for j in experience:
        a = parse_ym(j.get("from"))
        if not a:
            continue
        b = today if j.get("to") in (None, "") else (parse_ym(j.get("to")) or today)
        s, e = a[0] * 12 + a[1], b[0] * 12 + b[1]
        if e >= s:
            spans.append((s, e))
    if not spans:
        return None
    spans.sort()
    merged = [list(spans[0])]
    for s, e in spans[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return round(sum(e - s for s, e in merged) / 12, 1)


def check(seniority, years):
    """Return (kind, reason) if label and years disagree, else None.
    kind: 'hard' = tenure label breaks its own definition.
          'soft' = role label with thin tenure (legal, review-worthy)."""
    if years is None:
        return None                      # no dates -> nothing to compare (counted separately)
    # HARD — tenure-based labels vs their own definitions
    if seniority == "junior" and years > 2 + SLACK:
        return ("hard", f"junior but {years} yrs worked")
    if seniority == "mid" and years > 5 + SLACK:
        return ("hard", f"mid but {years} yrs worked")
    if seniority == "mid" and years < 2 - SLACK:
        return ("hard", f"mid but only {years} yrs worked")
    if seniority == "senior" and years < 5 - SLACK:
        return ("hard", f"senior but only {years} yrs worked")
    # SOFT — role-based labels: no year floor in the schema, flag gently
    if seniority in ("lead", "manager", "director", "executive") and years < 5 - SLACK:
        return ("soft", f"{seniority} at {years} yrs (legal — role-based; verify)")
    return None


rows = []
no_dates = 0
counts = {}
for pf in sorted(PROFILES.glob("*.json")):
    data = json.loads(pf.read_text(encoding="utf-8"))
    p = data.get("profile", data)
    sen = p.get("seniority")
    yrs = compute_years(p.get("experience", []))
    counts[sen] = counts.get(sen, 0) + 1
    if yrs is None and p.get("experience"):
        no_dates += 1
        continue
    result = check(sen, yrs)
    if result:
        kind, reason = result
        rows.append((kind, p.get("full_name") or pf.stem, sen, yrs, reason))

total = sum(counts.values())
hard = [r for r in rows if r[0] == "hard"]
soft = [r for r in rows if r[0] == "soft"]
print("=" * 70)
print("LAYER 3 — CONSISTENCY CHECK (computed years vs claimed seniority)")
print(f"  profiles checked      : {total}")
print(f"  HARD violations       : {len(hard)}  ({len(hard) / total * 100:.1f}%)  <- definition breaches")
print(f"  soft flags            : {len(soft)}  ({len(soft) / total * 100:.1f}%)  <- legal, verify by eye")
print(f"  no dates to compare   : {no_dates}")
print("-" * 70)
print("  seniority spread:", "  ".join(f"{k}:{v}" for k, v in sorted(counts.items(), key=lambda x: -x[1])))
for label, subset in (("HARD VIOLATIONS", hard), ("SOFT FLAGS", soft)):
    print("-" * 70)
    print(f"  {label} ({len(subset)}):")
    if subset:
        subset.sort(key=lambda r: -(r[3] or 0))
        print(f"  {'name':<34} {'label':<10} {'yrs':>5}   reason")
        for _, name, sen, yrs, reason in subset:
            print(f"  {name[:33]:<34} {sen:<10} {yrs:>5}   {reason}")
    else:
        print("  none")
print("=" * 70)
