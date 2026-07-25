"""
The Pool — Layer 2, the full-batch runner (v0.3)

Profiles the WHOLE pool: reads every .txt in extracted/, runs Pass 1 + Pass 2,
and saves one JSON profile per candidate to profiles/.

Like the intake engine, it's incremental and forgiving:
- A ledger (profiles_ledger.csv) records what's already profiled and skips it.
- Die halfway? Just run again — it picks up where it left off, re-paying nothing.
- Each profile is stamped with the schema version + source file, so when the
  schema changes you know which profiles are stale.
"""

import os
import sys
import csv
import json
import time
from pathlib import Path
from datetime import date, datetime

from dotenv import load_dotenv
from anthropic import Anthropic

sys.stdout.reconfigure(encoding="utf-8")

BASE = Path(__file__).parent
SCHEMA_DIR = BASE / "schema"
EXTRACTED = BASE / "extracted"
PROFILES = BASE / "profiles"
LEDGER = BASE / "profiles_ledger.csv"
PROFILES.mkdir(exist_ok=True)

sys.path.insert(0, str(SCHEMA_DIR))
from build_competency_schema import build_competency_schema   # noqa: E402

load_dotenv()
if not os.getenv("ANTHROPIC_API_KEY"):
    print("WARNING: no ANTHROPIC_API_KEY in .env — the run will fail.\n")
client = Anthropic(max_retries=8)   # ride out API 529 "Overloaded" spells

MODEL = "claude-sonnet-5"
# Bump this whenever the schema changes, so profiles record which version built them.
# v2.1: bare-year dates, Hijri, cert objects, courses, achievements, scope=built.
SCHEMA_VERSION = "2.1"

# Sonnet 5 intro pricing (per token). Update if pricing changes.
PRICE_IN = 2.0 / 1_000_000
PRICE_OUT = 10.0 / 1_000_000

# --- Load schema + hints (same as the profiler) ---
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
            "description": "Tag this job's competencies, from the allowed list only.",
            "input_schema": comp_schema}
    r = client.messages.create(
        model=MODEL, max_tokens=1024, system=PASS2_SYSTEM,
        tools=[tool], tool_choice={"type": "tool", "name": "tag_competencies"},
        messages=[{"role": "user", "content": job_evidence(job)}],
    )
    block = next((b for b in r.content if b.type == "tool_use"), None)
    comps = normalize_comps(block.input.get("competencies", []) if block else [])
    return comps, r.usage


# --- Load the ledger: which source files are already profiled? ---
done = set()
if LEDGER.exists():
    with LEDGER.open("r", newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            done.add(row["source_file"])

# Only profile CVs that actually have text (skip empty .txt from unreadable scans)
all_txt = sorted(p for p in EXTRACTED.glob("*.txt") if p.stat().st_size > 0)
todo = [p for p in all_txt if p.name not in done]

print(f"Pool: {len(all_txt)} CV texts | already profiled: {len(done)} | to do now: {len(todo)}\n")

ledger_is_new = not LEDGER.exists()
tot_in = tot_out = 0
ok = failed = 0
start = time.time()

with LEDGER.open("a", newline="", encoding="utf-8-sig") as ledger_file:
    writer = csv.writer(ledger_file)
    if ledger_is_new:
        writer.writerow(["source_file", "full_name", "jobs", "in_tokens", "out_tokens", "profiled_at"])

    for i, path in enumerate(todo, start=1):
        try:
            profile, u1 = run_pass1(path.read_text(encoding="utf-8"))
            cin, cout = u1.input_tokens, u1.output_tokens

            for job in profile.get("experience", []):
                comps, u2 = run_pass2(job)
                job["competencies"] = comps
                if u2:
                    cin += u2.input_tokens
                    cout += u2.output_tokens

            # stamp provenance, then save
            stamped = {
                "_meta": {
                    "source_file": path.name,
                    "schema_version": SCHEMA_VERSION,
                    "model": MODEL,
                    "profiled_at": datetime.now().isoformat(timespec="seconds"),
                    "status": "draft",   # draft until Layer 3 measures accuracy
                },
                "profile": profile,
            }
            out_path = PROFILES / (path.stem + ".json")
            out_path.write_text(json.dumps(stamped, ensure_ascii=False, indent=2), encoding="utf-8")

            writer.writerow([path.name, profile.get("full_name"),
                             len(profile.get("experience", [])), cin, cout,
                             stamped["_meta"]["profiled_at"]])
            ledger_file.flush()   # write the ledger row NOW, so a crash loses nothing

            tot_in += cin
            tot_out += cout
            ok += 1
            cost = tot_in * PRICE_IN + tot_out * PRICE_OUT
            print(f"[{i}/{len(todo)}] {profile.get('full_name') or path.stem}  "
                  f"({len(profile.get('experience', []))} jobs)  "
                  f"running cost ${cost:.2f}")

        except Exception as error:
            failed += 1
            print(f"[{i}/{len(todo)}] FAILED {path.name}: {error}")

elapsed = int(time.time() - start)
cost = tot_in * PRICE_IN + tot_out * PRICE_OUT
print("\n" + "=" * 60)
print(f"Done this run: {ok} profiled, {failed} failed, in {elapsed//60}m {elapsed%60}s")
print(f"Tokens: {tot_in:,} in + {tot_out:,} out")
print(f"Cost this run: ${cost:.2f}" + (f"  (~${cost/ok:.3f} per CV)" if ok else ""))
print(f"Profiles saved in: {PROFILES.name}/   ({len(list(PROFILES.glob('*.json')))} total)")
print("=" * 60)