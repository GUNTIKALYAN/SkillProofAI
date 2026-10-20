from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ExplanationItem(BaseModel):
    skill: str
    explanation: str = Field(max_length=400)


class Explanations(BaseModel):
    items: list[ExplanationItem]


class JobEntry(BaseModel):
    company: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=120)
    start: str
    end: str | None = None
    bullets: list[str] = Field(default_factory=list)


class ExperienceParse(BaseModel):
    entries: list[JobEntry]

    @model_validator(mode="before")
    @classmethod
    def _one_object(cls, value: object) -> object:
        if not isinstance(value, dict) or "entries" in value:
            return value
        jobs = value.get("jobs")
        if isinstance(jobs, list):
            return {"entries": jobs}
        if "company" in value and "title" in value:
            return {"entries": [value]}
        return value


class PlanItem(BaseModel):
    skill: str
    steps: list[str] = Field(min_length=1)
    resources: list[str] = Field(default_factory=list)


class ActionPlan(BaseModel):
    items: list[PlanItem]


CompanyStatus = Literal["found", "not_found", "ambiguous", "skipped"]
