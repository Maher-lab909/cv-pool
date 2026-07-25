"""
Pass 2 schema builder — competency SCOPE, v2.1.

Each tagged competency is an object {id, scope}, judged per competency per job.
scope = support / executed / built. The enum of ids is still locked per
job family (a nurse's job can only ever see nursing competencies).

v2.1 changes (settled in the scope session, PROGRESS_3):
- "strategic" renamed to "built" — the enum value goes into the prompt, and
  "built" has exactly one meaning: made it exist.
- "led the function" REMOVED from the triggers — leadership is a competency
  (team_leadership) and a seniority level, never a scope level.
- internship/co-op clause REMOVED from support — employment type is
  irrelevant; only the wording of the claim decides.
"""

import json
from pathlib import Path

COMPETENCIES = json.loads(
    (Path(__file__).parent / "competencies.json").read_text(encoding="utf-8")
)

SCOPE_DESCRIPTION = (
    "support ONLY if the CV uses explicit assist wording for this competency in "
    "this job (assisted, supported, participated in, helped, involved in). "
    "built ONLY with explicit creation/ownership wording (designed, established, "
    "defined, restructured, built the process). executed is the default: the "
    "person did the work themselves, or the competency is listed with no "
    "qualifier. Employment type is irrelevant -- an intern who 'prepared "
    "reports' is executed, not support. Assist wording is about the candidate's "
    "ROLE in the task, NOT the task name -- 'provided IT support to 500 users' "
    "is executed, not support. The word 'strategy' in a sentence is not by "
    "itself evidence -- 'contributed to the HR strategy' is not built. Leading "
    "or managing people is NOT a scope level -- it is the team_leadership "
    "competency where the family list has it; a manager supervising staff who "
    "never touched the design of the process is executed. If wording conflicts "
    "for the same competency in the same job, pick the highest level evidenced "
    "(support < executed < built). Job title and team size are irrelevant. "
    "If unsure, use executed."
)


def build_competency_schema(job_family: str) -> dict | None:
    """Tagging schema for one job's competencies, restricted to that family's
    list. Each competency carries a scope. None if the family has no list."""
    ids = [c["id"] for c in COMPETENCIES.get(job_family, [])]
    if not ids:
        return None

    return {
        "title": "competency_tagging",
        "type": "object",
        "additionalProperties": False,
        "required": ["competencies"],
        "properties": {
            "competencies": {
                "type": "array",
                "description": (
                    "Competencies evidenced by this job's title, responsibilities "
                    "and achievements, each with the level at which the candidate "
                    "performed it. Include a competency if it is clearly evidenced "
                    "-- INCLUDING assist-only mentions (tag those as support). "
                    "Empty array if none apply."
                ),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "scope"],
                    "properties": {
                        "id": {"type": "string", "enum": ids},
                        "scope": {
                            "type": "string",
                            "enum": ["support", "executed", "built"],
                            "description": SCOPE_DESCRIPTION,
                        },
                    },
                },
            }
        },
    }
