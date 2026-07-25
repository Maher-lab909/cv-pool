"""
The Pool — Layer 2 profiler — v0.4

Pass 2 tags each competency with a scope: support / executed / strategic,
judged ONLY by the wording of the claim (employment type and title are ignored).
compute_years sums ACTUAL months worked (merges overlaps, ignores gaps).

Runs on 7 people: the original 5, plus Abdulhadi and Alsahli whose CVs contain
explicit ownership wording -- so we can finally see `strategic` fire.
"""

import os
import sys
import json
from pathlib import Path
from datetime import date

from dotenv import load_dotenv
from anthropic import Anthropic

sys.stdout.reconfigure(encoding="utf-8")

BASE = Path(__file__).parent
SCHEMA_DIR = BASE / "schema"
EXTRACTED = BASE / "extracted"

sys.path.insert(0, str(SCHEMA_DIR))
from build_competency_schema import build_competency_schema   # noqa: E402

load_dotenv()
if not os.getenv("ANTHROPIC_API_KEY"):
    print("WARNING: no ANTHROPIC_API_KEY in .env — the profiler will fail.\n")
client = Anthropic(max_retries=8)   # ride out 529 "overloaded" spells

MODEL = "claude-sonnet-5"

TARGETS = [
    "network__Waleed Alasiri CV",
    "network__Rand Alsalem CV",
    "network__Majed_AL-Harbi_Resume",
    "network__Moath_Almotairi_CV_",
    "network__Layan Almotairi CV",
    "linkedin__2026 jan - 2026 jul__Abdulhadi CV",
    "linkedin__2026 jan - 2026 jul__Abdulaziz_Alsahli_Senior_Manager_Strategic_Development",
]

schema = json.loads((SCHEMA_DIR / "cv_extraction_schema.json").read_text(encoding="utf-8"))
job_families = json.loads((SCHEMA_DIR / "job_families.json").read_text(encoding="utf-8"))
industries = json.loads((SCHEMA_DIR / "industries.json").read_text(encoding="utf-8"))

jf_hints = "\n".join(
    f"- {jf['id']}: {', '.join(jf['example_titles'][:6])}" if jf["example_titles"]
    else f"- {jf['id']}"
    for jf in job_families
)
ind_hints = "\n".join(f"- {ind['id']}: {ind['examples']}" for ind in industries)

PASS1_SYSTEM = f"""You extract structured data from CVs. You are given the raw text of ONE CV and must call the save_cv_profile tool with the extracted information.

Core rules:
- Use ONLY information explicitly present in the CV text. Never invent, guess, or infer.
- If a value is not stated, use null / "unknown" / an empty array exactly as the schema allows. This includes nationality and location — never infer them from a name, phone code, or employer.
- Dates use YYYY-MM. If only a year is given, use the bare year YYYY — never invent a month. A currently-held job has "to": null.
- Rewrite each job's responsibilities into short, clean action-verb sentences, taken only from what the CV attributes to THAT job. Never move responsibilities between jobs or invent them.
- Classify each job's job_family by the actual WORK performed, and industry by the EMPLOYER, using the guides below.
- industry and job_family are SEPARATE menus. Never put a job_family value in the industry field. An advertising or marketing agency employer is media_entertainment.

Job family guide (pick the id whose typical titles match the work):
{jf_hints}

Industry guide (pick the id whose examples match the employer):
{ind_hints}
"""

PASS1_TOOL = {
    "name": "save_cv_profile",
    "description": "Save the structured profile extracted from this CV.",
    "input_schema": schema,
}

PASS2_SYSTEM = (
    "You tag the competencies demonstrated by ONE job. You are given the job's "
    "title, responsibilities and achievements, and an allowed list of competencies. "
    "For each competency the text clearly evidences, select it AND judge its scope "
    "-- the level at which the person performed it (support / executed / built), "
    "following the scope rules in the schema. Use ONLY competencies from the allowed "
    "list. Empty list if none clearly apply. Never guess."
)


def parse_ym(value):
    if not value:
        return None
    parts = str(value).split("-")
    try:
        return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 1)
    except (ValueError, IndexError):
        return None


def compute_years(experience):
    """Total ACTUAL months worked: sum each job, MERGING overlaps so concurrent
    jobs don't double-count and gaps between jobs don't count. Python only."""
    today = (date.today().year, date.today().month)
    spans = []
    for j in experience:
        a = parse_ym(j.get("from"))
        if not a:
            continue
        b = today if j.get("to") in (None, "") else (parse_ym(j.get("to")) or today)
        start, end = a[0] * 12 + a[1], b[0] * 12 + b[1]
        if end >= start:
            spans.append((start, end))
    if not spans:
        return None
    spans.sort()
    merged = [list(spans[0])]
    for s, e in spans[1:]:
        if s <= merged[-1][1]:              # overlap or touching -> merge
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    months = sum(e - s for s, e in merged)
    return round(months / 12, 1)


def run_pass1(cv_text):
    r = client.messages.create(
        model=MODEL, max_tokens=8192, system=PASS1_SYSTEM,
        tools=[PASS1_TOOL], tool_choice={"type": "tool", "name": "save_cv_profile"},
        messages=[{"role": "user", "content": cv_text}],
    )
    block = next((b for b in r.content if b.type == "tool_use"), None)
    if block is None:
        raise RuntimeError("Pass 1 returned no profile")
    return block.input, r.usage


def job_evidence(job):
    lines = [f"Title: {job.get('title')}"]
    if job.get("responsibilities"):
        lines.append("Responsibilities:")
        lines += [f"- {x}" for x in job["responsibilities"]]
    if job.get("achievements"):
        lines.append("Achievements:")
        lines += [f"- {x}" for x in job["achievements"]]
    if job.get("tools_used"):
        lines.append("Tools used: " + ", ".join(job["tools_used"]))
    return "\n".join(lines)


def normalize_comps(raw):
    """The model occasionally wraps its answer twice, as a dict OR as a JSON
    string. Unwrap either, so tags never get stored in an unreadable shape."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return []
    if isinstance(raw, dict):
        raw = raw.get("competencies", [])
    return raw if isinstance(raw, list) else []


def run_pass2(job):
    comp_schema = build_competency_schema(job.get("job_family"))
    if comp_schema is None:
        return [], None
    tool = {"name": "tag_competencies",
            "description": "Tag this job's competencies with their scope, from the allowed list only.",
            "input_schema": comp_schema}
    r = client.messages.create(
        model=MODEL, max_tokens=1024, system=PASS2_SYSTEM,
        tools=[tool], tool_choice={"type": "tool", "name": "tag_competencies"},
        messages=[{"role": "user", "content": job_evidence(job)}],
    )
    block = next((b for b in r.content if b.type == "tool_use"), None)
    comps = normalize_comps(block.input.get("competencies", []) if block else [])
    return comps, r.usage


def fmt_comp(c):
    return f"{c.get('id')}·{c.get('scope')}" if isinstance(c, dict) else str(c)


def show(profile):
    def val(x):
        return x if x else "— not stated"
    langs = ", ".join(f"{l['lang']} ({l['level']})" for l in profile.get("languages", [])) or "—"
    skills = profile.get("skills", [])
    years = compute_years(profile.get("experience", []))
    years_str = f"~{years} yrs" if years is not None else "n/a"
    print(f"Name:        {val(profile.get('full_name'))}")
    print(f"Current:     {val(profile.get('current_title'))}   |   "
          f"seniority: {profile.get('seniority')}  ({years_str} worked)")
    print(f"Location:    {val(profile.get('location'))}   |   Nationality: {val(profile.get('nationality'))}")
    print(f"Languages:   {langs}")
    print(f"Skills ({len(skills)}): {', '.join(skills) if skills else '—'}")
    print("Experience:")
    for job in profile.get("experience", []):
        to = job.get("to") or "present"
        comps = job.get("competencies", [])
        comps_str = ", ".join(fmt_comp(c) for c in comps) if comps else "—"
        print(f"   • {job.get('title')} @ {val(job.get('company'))}  "
              f"[{job.get('industry')}/{job.get('job_family')}]  {val(job.get('from'))}–{to}")
        print(f"       {comps_str}")
    print(f"Summary:     {profile.get('summary')}")


p1_in = p1_out = p2_in = p2_out = p2_calls = 0
scope_tally = {}

for i, name in enumerate(TARGETS, start=1):
    path = EXTRACTED / f"{name}.txt"
    print("\n" + "=" * 66)
    print(f"[{i}/{len(TARGETS)}]  {name}")
    print("-" * 66)
    if not path.exists():
        print(f"  !! not found: {path.name}")
        continue
    try:
        profile, u1 = run_pass1(path.read_text(encoding="utf-8"))
        p1_in += u1.input_tokens
        p1_out += u1.output_tokens
        for job in profile.get("experience", []):
            comps, u2 = run_pass2(job)
            job["competencies"] = comps
            for c in comps:
                if isinstance(c, dict):
                    s = c.get("scope")
                    scope_tally[s] = scope_tally.get(s, 0) + 1
            if u2:
                p2_calls += 1
                p2_in += u2.input_tokens
                p2_out += u2.output_tokens
        show(profile)
    except Exception as error:
        print(f"  FAILED: {error}")

print("\n" + "=" * 66)
print("SCOPE SPREAD across this run:")
total = sum(scope_tally.values()) or 1
for s in ["support", "executed", "built"]:
    n = scope_tally.get(s, 0)
    print(f"   {s:<10}: {n:>3}  ({n/total*100:.0f}%)")
print("-" * 66)
print(f"Pass 1: {p1_in:,} in + {p1_out:,} out ({len(TARGETS)} calls) | "
      f"Pass 2: {p2_in:,} in + {p2_out:,} out ({p2_calls} calls)")
print("=" * 66)