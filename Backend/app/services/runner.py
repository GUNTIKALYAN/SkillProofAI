import logging
import threading
import time
import uuid

from app.agents.graph import get_graph
from app.agents.skills.loader import allowlist, load_skills, skill_hash
from app.agents.trace import write_step
from app.config import get_settings
from app.db.models import AgentRun, Analysis
from app.db.session import session_scope
from app.mcp_client.context import RunContext, reset_llm, reset_run, set_llm, set_run
from app.mcp_client.transport import HttpTransport
from app.schemas.output_schema import AnalyzeResponse
from app.services.bucket import RedisBucket
from app.services.cache import RedisCache
from app.services.unknown_skills import save_unknown_skills

logger = logging.getLogger(__name__)


def execute_analysis(
    analysis_id: str,
    *,
    transport: object | None = None,
    llm: object | None = None,
    cache: object | None = None,
    bucket: object | None = None,
) -> None:
    settings = get_settings()
    skills = load_skills()
    token_run = None
    token_llm = None
    with session_scope() as session:
        row = session.get(Analysis, uuid.UUID(analysis_id))
        if row is None:
            logger.error("analysis missing id=%s", analysis_id)
            return
        row.status = "running"
        run = AgentRun(
            analysis_id=row.id,
            skill_hash=skill_hash(skills),
            status="running",
        )
        session.add(run)
        session.commit()
        ctx = RunContext(
            run_id=run.id,
            session=session,
            allow=allowlist(skills),
            limits={name: skill.limits["max_tool_calls"] for name, skill in skills.items()},
            budget=settings.tool_budget,
            transport=transport or HttpTransport(),
            bucket=bucket or RedisBucket(settings.redis_url),
            cache=cache or RedisCache(settings.redis_url),
            lock=threading.Lock(),
            node_calls={},
        )
        token_run = set_run(ctx)
        if llm is not None:
            token_llm = set_llm(llm)
        try:
            state = get_graph().invoke(_initial(row), {"recursion_limit": 20})
            _save(session, row, run, state)
        except Exception as exc:  # noqa: BLE001 - a failed graph must be stored, not raised to the user
            logger.error("analysis failed id=%s error=%s", analysis_id, type(exc).__name__)
            row.status = "failed"
            row.result_json = {"partial": True, "error": "Analysis failed"}
            run.status = "failed"
            write_step("runner", 1, None, {"id": analysis_id}, None, 0, time.perf_counter(), type(exc).__name__)
        finally:
            if token_llm is not None:
                reset_llm(token_llm)
            if token_run is not None:
                reset_run(token_run)


def _initial(row: Analysis) -> dict:
    resume = row.resume_json or {}
    experience = resume.get("experience") or []
    return {
        "step_count": 0,
        "github_username": row.github_username,
        "has_experience": bool(experience),
        "resume": resume,
        "jd_text": row.jd_text,
        "match_retries": 0,
        "github_skipped": row.github_username is None,
        "experience_skipped": not experience,
    }


def _save(session, row: Analysis, run: AgentRun, state: dict) -> None:
    match = state.get("match") or {}
    score = match.get("score")
    audit_items = (state.get("audit") or {}).get("items") or []
    unknown = match.get("unknown_skills") or []
    if isinstance(score, dict) and score.get("label"):
        body = AnalyzeResponse.model_validate(
            {
                "jd_match_score": score,
                "audit": audit_items,
                "unknown_skills": unknown,
            }
        ).model_dump()
        body["github_skipped"] = bool(state.get("github_skipped"))
        body["experience_skipped"] = bool(state.get("experience_skipped"))
        body["github"] = state.get("github_evidence")
        body["action_plan"] = state.get("plan")
        body["companies"] = (state.get("experience") or {}).get("companies") or []
        body["partial"] = bool(match.get("error") or state.get("audit_error"))
        row.result_json = body
        row.score = float(score.get("score") or 0)
        row.status = "completed"
        run.status = "completed"
        save_unknown_skills(session, unknown)
        return
    row.status = "failed"
    run.status = "failed"
    row.result_json = {
        "partial": True,
        "error": "Analysis is incomplete",
        "github_skipped": bool(state.get("github_skipped")),
        "experience_skipped": bool(state.get("experience_skipped")),
    }
    logger.error("analysis incomplete id=%s", row.id)
