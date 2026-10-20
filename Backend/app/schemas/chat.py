import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    analysis_id: uuid.UUID | None = None


class ChatMessagePublic(BaseModel):
    role: str
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatToolCall(BaseModel):
    name: Literal["explain_skill", "related_skills", "what_if_learn"]
    skill: str = Field(min_length=1, max_length=80)


class ChatReplyPublic(BaseModel):
    text: str
    before: float | None = None
    after: float | None = None
    skill: str | None = None


class ChatDraft(BaseModel):
    answer: str = Field(min_length=1, max_length=2000)
    citations: list[str] = Field(default_factory=list)
    tool: ChatToolCall | None = None


class CompareRequest(BaseModel):
    job_descriptions: list[str] = Field(min_length=2, max_length=10)
    analysis_id: uuid.UUID | None = None


class ComparedJob(BaseModel):
    index: int
    preview: str
    score: float


class CompareResponse(BaseModel):
    ranked: list[ComparedJob]
    unlock_skill: str | None
    unlock_jobs: int


class PlanCheck(BaseModel):
    skill: str = Field(min_length=1, max_length=80)
    step: str = Field(min_length=1, max_length=400)
    done: bool
