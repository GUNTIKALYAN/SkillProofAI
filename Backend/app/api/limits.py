import logging
import uuid

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import AuditLog, User
from app.db.session import get_db
from app.services.rate_limit import RateLimitError, get_limiter

logger = logging.getLogger(__name__)

_RATE_LIMIT = "rate_limit"


async def limit_auth(request: Request, session: Session = Depends(get_db)) -> None:
    email = await _email(request)
    identity = f"{_client_ip(request)}:{email}"
    _enforce(session, "auth", identity, _user_id(session, email))


def limit_analyze(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> User:
    _enforce(session, "analyze", str(user.id), user.id)
    return user


def limit_chat(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> User:
    _enforce(session, "chat", str(user.id), user.id)
    return user


def _enforce(
    session: Session,
    endpoint: str,
    identity: str,
    user_id: uuid.UUID | None,
) -> None:
    try:
        retry = get_limiter().take(endpoint, identity)
    except RateLimitError as exc:
        logger.error("rate limiter unavailable endpoint=%s error=%s", endpoint, type(exc).__name__)
        raise HTTPException(status_code=503, detail="Rate limiter is unavailable") from exc
    if retry is None:
        return
    logger.info("rate limit hit endpoint=%s", endpoint)
    _record(session, endpoint, user_id)
    raise HTTPException(
        status_code=429,
        detail="Too many requests",
        headers={"Retry-After": str(retry)},
    )


def _record(session: Session, endpoint: str, user_id: uuid.UUID | None) -> None:
    session.add(AuditLog(user_id=user_id, action=_RATE_LIMIT, target=endpoint))
    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        logger.error("audit log failed error=%s", type(exc).__name__)


async def _email(request: Request) -> str:
    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type:
        return ""
    try:
        body = await request.json()
    except ValueError:
        return ""
    if not isinstance(body, dict):
        return ""
    email = body.get("email")
    if not isinstance(email, str):
        return ""
    return email.strip().lower()


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[-1].strip() or "unknown"
    if request.client is None:
        return "unknown"
    return request.client.host


def _user_id(session: Session, email: str) -> uuid.UUID | None:
    if not email:
        return None
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        return None
    return user.id
