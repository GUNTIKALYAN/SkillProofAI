from typing import Literal

from pydantic import BaseModel, Field

MatchKind = Literal["exact", "alias", "neighbour", "missing", "unknown"]
Priority = Literal["required", "preferred"]
AuditStatus = Literal["matched", "partial", "missing"]
JD_MATCH_LABEL = "JD Match Score"


class JdSkill(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    priority: Priority


class BreakdownItem(BaseModel):
    skill: str
    canonical: str | None
    priority: Priority
    points: float
    kind: MatchKind
    reason: str


class ScoreMatch(BaseModel):
    label: str = JD_MATCH_LABEL
    score: float
    breakdown: list[BreakdownItem]


class AuditItem(BaseModel):
    skill: str
    status: AuditStatus
    reason: str


class AuditResult(BaseModel):
    items: list[AuditItem]


class CanonicalSkill(BaseModel):
    input: str
    key: str
    known: bool
    canonical: str | None
    category: str | None
    match: Literal["exact", "alias", "unknown"]
    ancestors: list[str]


class RelatedItem(BaseModel):
    skill: str
    relation: str
    weight: float


class RelatedSkills(BaseModel):
    skill: str
    known: bool
    related: list[RelatedItem]


class ExplainSkill(BaseModel):
    input: str
    known: bool
    canonical: str | None
    category: str | None
    match: Literal["exact", "alias", "unknown"]
    aliases: list[str]
    ancestors: list[str]
    relations: list[RelatedItem]


class WhatIfLearn(BaseModel):
    skill: str
    known: bool
    before: float
    after: float
    delta: float
    breakdown: list[BreakdownItem]
