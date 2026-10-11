import hashlib
import logging
import uuid

from sqlalchemy.orm import Session

from app.db.models import Analysis
from app.schemas.input_schema import AnalyzeRequest
from app.services.jobs import QueueError, enqueue_analysis

logger = logging.getLogger(__name__)


def accept_analysis(
    session: Session,
    user_id: uuid.UUID,
    request: AnalyzeRequest,
    resume: dict,
) -> uuid.UUID:
    username = request.github_username
    row = Analysis(
        user_id=user_id,
        jd_text=request.jd_text,
        jd_hash=hashlib.sha256(request.jd_text.encode()).hexdigest(),
        github_username=username,
        resume_json=resume,
        status="queued",
    )
    session.add(row)
    session.commit()
    try:
        enqueue_analysis(row.id)
    except QueueError:
        row.status = "failed"
        session.commit()
        raise
    logger.info("analysis queued id=%s", row.id)
    return row.id
