import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Analysis


def get_owned_analysis(
    session: Session,
    user_id: uuid.UUID,
    analysis_id: uuid.UUID,
) -> Analysis | None:
    return session.scalar(
        select(Analysis).where(
            Analysis.id == analysis_id,
            Analysis.user_id == user_id,
        )
    )
