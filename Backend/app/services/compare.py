import uuid

from sqlalchemy.orm import Session

from app.db.models import Analysis, User
from app.llm.complete import LlmError
from app.mcp_client import McpError, call_tool
from app.schemas.chat import ComparedJob, CompareResponse
from app.services.analysis_access import completed_analysis
from app.services.chat import NoAnalysis
from app.services.skill_extract import ExtractionError, extract_skills
from app.services.tool_session import Clients, default_clients, tool_session

_PREVIEW = 80


class CompareFailed(Exception):
    pass


def compare_jobs(
    session: Session,
    user: User,
    jobs: list[str],
    analysis_id: uuid.UUID | None,
    clients: Clients | None = None,
) -> CompareResponse:
    row = completed_analysis(session, user.id, analysis_id)
    if row is None:
        raise NoAnalysis
    cleaned = [job.strip() for job in jobs]
    if any(len(job) < 10 for job in cleaned):
        raise ValueError("Each job description must be at least 10 characters")
    resume = _resume_text(row)
    used = clients or default_clients()
    try:
        with tool_session("compare", session, used):
            ranked, counts = _score_jobs(resume, row.result_json or {}, cleaned)
    except (LlmError, ExtractionError, McpError) as exc:
        raise CompareFailed from exc
    unlock_skill, unlock_jobs = _unlock(counts)
    return CompareResponse(ranked=ranked, unlock_skill=unlock_skill, unlock_jobs=unlock_jobs)


def _score_jobs(resume: str, result: dict, jobs: list[str]) -> tuple[list[ComparedJob], dict[str, int]]:
    stored = [str(skill) for skill in result.get("resume_skills") or []]
    ranked: list[ComparedJob] = []
    counts: dict[str, int] = {}
    for index, job in enumerate(jobs, start=1):
        extraction = extract_skills(resume, job)
        candidate = stored or extraction.resume_skills
        score = call_tool(
            "skillgraph",
            "score_match",
            {
                "jd_skills": [item.model_dump() for item in extraction.jd_skills],
                "candidate_skills": candidate,
            },
            "compare",
        )
        ranked.append(
            ComparedJob(index=index, preview=job[:_PREVIEW], score=float(score.get("score") or 0))
        )
        for item in score.get("breakdown") or []:
            if not isinstance(item, dict) or float(item.get("points") or 0) >= 1:
                continue
            name = str(item.get("canonical") or item.get("skill") or "").strip()
            if name:
                counts[name] = counts.get(name, 0) + 1
    ranked.sort(key=lambda item: (-item.score, item.index))
    return ranked, counts


def _unlock(counts: dict[str, int]) -> tuple[str | None, int]:
    if not counts:
        return None, 0
    skill = min(counts, key=lambda name: (-counts[name], name))
    return skill, counts[skill]


def _resume_text(row: Analysis) -> str:
    resume = row.resume_json or {}
    text = resume.get("text") or []
    if isinstance(text, list):
        return "\n".join(str(line) for line in text)
    return str(text)
