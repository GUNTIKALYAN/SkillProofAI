import logging
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.llm.complete import LlmError, complete_json

logger = logging.getLogger(__name__)

_MAX_CHARS = 20_000


class ExtractionError(Exception):
    pass


class JdSkill(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    priority: Literal["required", "preferred"]


class SkillExtraction(BaseModel):
    resume_skills: list[str]
    jd_skills: list[JdSkill]


def extract_skills(resume_text: str, jd_text: str) -> SkillExtraction:
    payload = {
        "resume": clip_text(resume_text, "resume"),
        "job_description": clip_text(jd_text, "job description"),
    }
    try:
        model, _tokens = complete_json("match_score", payload, SkillExtraction)
    except (LlmError, ValidationError) as exc:
        logger.error("skill extraction failed error=%s", type(exc).__name__)
        raise ExtractionError("Skill extraction failed") from exc
    if not isinstance(model, SkillExtraction):
        raise ExtractionError("Skill extraction failed")
    return model


def clip_text(text: str, label: str) -> str:
    if len(text) <= _MAX_CHARS:
        return text
    logger.info("text clipped source=%s chars=%s", label, len(text))
    return text[:_MAX_CHARS]
