import logging
import time

from pydantic import ValidationError

from app.agents.trace import write_step
from app.llm.complete import LlmError, complete_json
from app.mcp_client import McpError, call_tool
from app.services.skill_extract import SkillExtraction, clip_text

logger = logging.getLogger(__name__)


def match_score(state: dict) -> dict:
    started = time.perf_counter()
    payload = {
        "resume_chars": len(_resume_text(state)),
        "jd_chars": len(state.get("jd_text") or ""),
    }
    try:
        extraction, tokens = complete_json(
            "match_score",
            {
                "resume": clip_text(_resume_text(state), "resume"),
                "job_description": clip_text(state.get("jd_text") or "", "job description"),
            },
            SkillExtraction,
        )
        known, unknown = _canonicalize(extraction)
        score = call_tool(
            "skillgraph",
            "score_match",
            {
                "jd_skills": [item.model_dump() for item in extraction.jd_skills],
                "candidate_skills": extraction.resume_skills,
            },
            "match_score",
        )
        low = _low(extraction, known)
        retries = int(state.get("match_retries") or 0)
        previous = state.get("match") or {}
        if previous.get("low_confidence"):
            retries += 1
        result = {
            "extraction": extraction.model_dump(),
            "score": score,
            "unknown_skills": unknown,
            "low_confidence": low,
        }
        write_step("match_score", 1, None, payload, {"score": score.get("score"), "low_confidence": low}, tokens, started, None)
        return {"match": result, "match_retries": retries}
    except (McpError, LlmError, ValidationError) as exc:
        logger.error("match score failed error=%s", type(exc).__name__)
        write_step("match_score", 1, None, payload, None, 0, started, type(exc).__name__)
        return {
            "match": {"error": "Match score is unavailable", "low_confidence": False, "unknown_skills": []},
            "match_retries": 1,
        }


def _canonicalize(extraction: SkillExtraction) -> tuple[dict[str, bool], list[str]]:
    known: dict[str, bool] = {}
    unknown: list[str] = []
    names = list(extraction.resume_skills)
    names.extend(item.name for item in extraction.jd_skills)
    seen: set[str] = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        found = call_tool("skillgraph", "canonicalize_skill", {"text": name}, "match_score")
        is_known = bool(found.get("known"))
        known[name] = is_known
        key = found.get("key")
        if not is_known and isinstance(key, str) and key and key not in unknown:
            unknown.append(key)
    return known, sorted(unknown)


def _low(extraction: SkillExtraction, known: dict[str, bool]) -> bool:
    if not extraction.jd_skills:
        return True
    unknown = sum(1 for item in extraction.jd_skills if not known.get(item.name, False))
    return unknown * 2 >= len(extraction.jd_skills)


def _resume_text(state: dict) -> str:
    resume = state.get("resume") or {}
    raw = resume.get("text") or []
    if raw:
        return "\n".join(str(line) for line in raw)
    lines: list[str] = []
    for key in ("skills", "projects", "experience"):
        lines.extend(str(line) for line in resume.get(key) or [])
    return "\n".join(lines)
