import logging
import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.db.models import (
    AgentRun,
    AgentStep,
    Analysis,
    AuditLog,
    ChatMessage,
    ChatSession,
    RefreshToken,
    User,
)

logger = logging.getLogger(__name__)


def delete_owned(session: Session, user_id: uuid.UUID) -> None:
    session_ids = list(session.scalars(select(ChatSession.id).where(ChatSession.user_id == user_id)))
    if session_ids:
        session.execute(delete(ChatMessage).where(ChatMessage.session_id.in_(session_ids)))
        session.execute(delete(ChatSession).where(ChatSession.user_id == user_id))
    analysis_ids = list(session.scalars(select(Analysis.id).where(Analysis.user_id == user_id)))
    if analysis_ids:
        run_ids = list(session.scalars(select(AgentRun.id).where(AgentRun.analysis_id.in_(analysis_ids))))
        if run_ids:
            session.execute(delete(AgentStep).where(AgentStep.run_id.in_(run_ids)))
            session.execute(delete(AgentRun).where(AgentRun.analysis_id.in_(analysis_ids)))
        session.execute(delete(Analysis).where(Analysis.user_id == user_id))
    session.execute(delete(RefreshToken).where(RefreshToken.user_id == user_id))
    session.execute(update(AuditLog).where(AuditLog.user_id == user_id).values(user_id=None))
    session.execute(update(AuditLog).where(AuditLog.admin_id == user_id).values(admin_id=None))


def delete_account(session: Session, user: User) -> None:
    user_id = user.id
    delete_owned(session, user_id)
    session.delete(user)
    session.commit()
    logger.info("account deleted id=%s", user_id)
