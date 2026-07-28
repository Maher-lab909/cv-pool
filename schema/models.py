"""
Layer 3 — the Pydantic mirror of the CV extraction schema (v2.1).

Validates a stored profile IN PYTHON, catching what the model's tool schema only
strongly hints at: invalid enum values, malformed dates, broken structure. The
enum sets are loaded FROM cv_extraction_schema.json, so the mirror can never drift
from the schema (the JSON stays the single source of truth).

Tolerant on version-diff fields (v2 vs v2.1: certifications as str-or-object,
courses/achievements absent, competencies plain-or-scoped) so it validates the
existing pool AND guards future runs. Any ValidationError is therefore a REAL
problem, not version noise.
"""

import re
import json
from pathlib import Path
from typing import Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_DIR = Path(__file__).parent
_s = json.loads((SCHEMA_DIR / "cv_extraction_schema.json").read_text(encoding="utf-8"))
_p = _s["properties"]
_e = _p["experience"]["items"]["properties"]

# enum sets pulled straight from the schema (single source of truth)
SENIORITY  = set(_p["seniority"]["enum"])
DEGREE     = set(_p["education"]["items"]["properties"]["degree"]["enum"])
LANG_LEVEL = {x for x in _p["languages"]["items"]["properties"]["level"]["enum"] if x is not None}
INDUSTRY   = set(_e["industry"]["enum"])
JOB_FAMILY = set(_e["job_family"]["enum"])
SCOPE      = {"support", "executed", "built"}        # from build_competency_schema.py
DATE_RE    = re.compile(_e["from"]["pattern"])       # ^\d{4}(-\d{2})?$


def _in(value, allowed, label):
    if value not in allowed:
        raise ValueError(f"{label} '{value}' is not in the allowed menu")
    return value


class Language(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lang: str
    level: Optional[str] = None

    @field_validator("level")
    @classmethod
    def _v(cls, v):
        return v if v is None else _in(v, LANG_LEVEL, "language level")


class Education(BaseModel):
    model_config = ConfigDict(extra="forbid")
    degree: str
    field: Optional[str] = None
    institution: Optional[str] = None
    year: Optional[int] = None

    @field_validator("degree")
    @classmethod
    def _v(cls, v):
        return _in(v, DEGREE, "degree")


class Certification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    status: str

    @field_validator("status")
    @classmethod
    def _v(cls, v):
        return _in(v, {"completed", "ongoing"}, "cert status")


class Competency(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    scope: str

    @field_validator("scope")
    @classmethod
    def _v(cls, v):
        return _in(v, SCOPE, "scope")


class Experience(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    title: str
    company: Optional[str] = None
    industry: str
    job_family: str
    from_: Optional[str] = Field(default=None, alias="from")
    to: Optional[str] = None
    responsibilities: list[str] = []
    achievements: list[str] = []
    tools_used: list[str] = []
    # added by Pass 2 and merged into the stored profile; plain (v2) or scoped (v2.1)
    competencies: list[Union[Competency, str]] = []

    @field_validator("industry")
    @classmethod
    def _ind(cls, v):
        return _in(v, INDUSTRY, "industry")

    @field_validator("job_family")
    @classmethod
    def _fam(cls, v):
        return _in(v, JOB_FAMILY, "job_family")

    @field_validator("from_", "to")
    @classmethod
    def _date(cls, v):
        if v is not None and not DATE_RE.match(v):
            raise ValueError(f"date '{v}' is not YYYY or YYYY-MM")
        return v


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    nationality: Optional[str] = None
    current_title: Optional[str] = None
    seniority: str
    summary: str
    skills: list[str] = []
    languages: list[Language] = []
    education: list[Education] = []
    certifications: list[Union[Certification, str]] = []
    courses: list[str] = []          # v2.1; absent in v2 -> defaults to []
    achievements: list[str] = []     # v2.1; absent in v2 -> defaults to []
    experience: list[Experience] = []

    @field_validator("seniority")
    @classmethod
    def _sen(cls, v):
        return _in(v, SENIORITY, "seniority")
