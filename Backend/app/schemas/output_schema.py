from typing import Literal

from pydantic import BaseModel, ConfigDict


class SkillBreakdown(BaseModel):
    skill: str
    canonical: str | None = None
    priority: Literal["required", "preferred"]
    points: float
    kind: str
    reason: str

    model_config = ConfigDict(extra="ignore")


class JdMatchScore(BaseModel):
    label: str
    score: float
    breakdown: list[SkillBreakdown]

    model_config = ConfigDict(extra="ignore")


class AuditEntry(BaseModel):
    skill: str
    status: str
    reason: str

    model_config = ConfigDict(extra="ignore")


class AnalyzeResponse(BaseModel):
    jd_match_score: JdMatchScore
    audit: list[AuditEntry]
    unknown_skills: list[str]
