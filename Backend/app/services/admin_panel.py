import logging
import math
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.skills_loader import load_skills
from app.db import (
    ROLE_ADMIN,
    STATUS_ACTIVE,
    STATUS_BLOCKED,
    AgentRun,
    AgentStep,
    Analysis,
    ChatMessage,
    ChatSession,
    User,
)
from app.services.account import delete_owned

logger = logging.getLogger(__name__)

_TRACE_LIMIT = 50


class AdminProtected(Exception):
    pass


class MissingUser(Exception):
    pass


def overview(session: Session) -> dict:
    users = _count(session, User)
    analyses = _count(session, Analysis)
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    analyses_today = int(
        session.scalar(select(func.count()).select_from(Analysis).where(Analysis.created_at >= start)) or 0
    )
    average = session.scalar(select(func.avg(Analysis.score)).where(Analysis.score.is_not(None)))
    failed = int(
        session.scalar(select(func.count()).select_from(Analysis).where(Analysis.status == "failed")) or 0
    )
    tokens = int(session.scalar(select(func.coalesce(func.sum(AgentStep.tokens), 0))) or 0)
    latencies = [int(value) for value in session.scalars(select(AgentStep.latency_ms))]
    return {
        "users": users,
        "analyses": analyses,
        "analyses_today": analyses_today,
        "average_score": float(average or 0),
        "failed": failed,
        "error_rate": (failed / analyses) if analyses else 0,
        "tokens": tokens,
        "p95_latency_ms": _p95(latencies),
    }


def search_users(session: Session, query: str) -> list[dict]:
    statement = select(User).order_by(User.created_at.desc())
    if query.strip():
        statement = statement.where(User.email.contains(query.strip().lower()))
    rows = []
    for user in session.scalars(statement):
        rows.append(
            {
                "id": user.id,
                "email": user.email,
                "role": user.role,
                "status": user.status,
                "analyses": _count_where(session, Analysis, Analysis.user_id == user.id),
                "chats": _chat_count(session, user.id),
                "tokens": _user_tokens(session, user.id),
            }
        )
    return rows


def set_block(session: Session, admin_id: uuid.UUID, user_id: uuid.UUID, blocked: bool) -> User:
    user = _editable(session, user_id)
    user.status = STATUS_BLOCKED if blocked else STATUS_ACTIVE
    logger.info("user status changed admin=%s user=%s blocked=%s", admin_id, user.id, blocked)
    session.commit()
    return user


def remove_user(session: Session, admin_id: uuid.UUID, user_id: uuid.UUID) -> None:
    user = _editable(session, user_id)
    logger.info("user deleted admin=%s user=%s", admin_id, user.id)
    session.flush()
    delete_owned(session, user.id)
    session.delete(user)
    session.commit()


def list_traces(session: Session) -> list[dict]:
    rows = session.execute(
        select(AgentRun, User.email)
        .join(Analysis, Analysis.id == AgentRun.analysis_id)
        .join(User, User.id == Analysis.user_id)
        .order_by(AgentRun.created_at.desc())
        .limit(_TRACE_LIMIT)
    )
    return [
        {
            "id": run.id,
            "analysis_id": run.analysis_id,
            "email": email,
            "status": run.status,
            "skill_hash": run.skill_hash,
            "created_at": run.created_at,
        }
        for run, email in rows
    ]


def trace_detail(session: Session, run_id: uuid.UUID) -> dict | None:
    run = session.get(AgentRun, run_id)
    if run is None:
        return None
    steps = session.scalars(
        select(AgentStep).where(AgentStep.run_id == run.id).order_by(AgentStep.created_at)
    )
    return {
        "id": run.id,
        "analysis_id": run.analysis_id,
        "status": run.status,
        "skill_hash": run.skill_hash,
        "created_at": run.created_at,
        "steps": [
            {
                "node": step.node,
                "attempt": step.attempt,
                "tool": step.tool,
                "tokens": step.tokens,
                "latency_ms": step.latency_ms,
                "error": step.error,
                "output": step.output_json,
            }
            for step in steps
        ],
    }


def agent_files() -> list[dict]:
    skills = load_skills()
    return [
        {
            "name": skill.name,
            "description": skill.description,
            "tools": list(skill.tools),
            "limits": skill.limits,
            "hash": skill.digest.hex(),
        }
        for skill in skills.values()
    ]


def _editable(session: Session, user_id: uuid.UUID) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise MissingUser
    if user.role == ROLE_ADMIN:
        raise AdminProtected
    return user


def _chat_count(session: Session, user_id: uuid.UUID) -> int:
    total = session.scalar(
        select(func.count())
        .select_from(ChatMessage)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .where(ChatSession.user_id == user_id)
    )
    return int(total or 0)


def _user_tokens(session: Session, user_id: uuid.UUID) -> int:
    total = session.scalar(
        select(func.coalesce(func.sum(AgentStep.tokens), 0))
        .join(AgentRun, AgentRun.id == AgentStep.run_id)
        .join(Analysis, Analysis.id == AgentRun.analysis_id)
        .where(Analysis.user_id == user_id)
    )
    return int(total or 0)


def _count(session: Session, model: type) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _count_where(session: Session, model: type, clause: object) -> int:
    return int(session.scalar(select(func.count()).select_from(model).where(clause)) or 0)


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return ordered[index]
