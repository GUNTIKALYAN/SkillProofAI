from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import ROLE_USER, STATUS_ACTIVE, RefreshToken, User
from app.services.passwords import hash_password, verify_password
from app.services.tokens import (
    create_access_token,
    hash_refresh_token,
    new_refresh_token,
    refresh_expires_at,
)


class InvalidCredentials(Exception):
    pass


class EmailTaken(Exception):
    pass


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    refresh_token: str


def register_user(session: Session, email: str, password: str) -> IssuedTokens:
    user = User(email=email, password_hash=hash_password(password), role=ROLE_USER)
    session.add(user)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise EmailTaken from exc
    issued = _issue(session, user)
    session.commit()
    return issued


def login_user(session: Session, email: str, password: str) -> IssuedTokens:
    user = session.scalar(select(User).where(User.email == email))
    if user is None or user.status != STATUS_ACTIVE or not verify_password(password, user.password_hash):
        raise InvalidCredentials
    user.last_login = datetime.now(timezone.utc)
    issued = _issue(session, user)
    session.commit()
    return issued


def refresh_session(session: Session, raw_token: str) -> IssuedTokens:
    row = _find_token(session, raw_token)
    now = datetime.now(timezone.utc)
    if row is None or row.revoked_at is not None or _aware(row.expires_at) <= now:
        raise InvalidCredentials
    user = session.get(User, row.user_id)
    if user is None or user.status != STATUS_ACTIVE:
        raise InvalidCredentials
    row.revoked_at = now
    issued = _issue(session, user)
    session.commit()
    return issued


def revoke_refresh_token(session: Session, raw_token: str) -> None:
    row = _find_token(session, raw_token)
    if row is None or row.revoked_at is not None:
        return
    row.revoked_at = datetime.now(timezone.utc)
    session.commit()


def _issue(session: Session, user: User) -> IssuedTokens:
    raw = new_refresh_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw),
            expires_at=refresh_expires_at(),
        )
    )
    return IssuedTokens(
        access_token=create_access_token(user.id, user.role),
        refresh_token=raw,
    )


def _find_token(session: Session, raw_token: str) -> RefreshToken | None:
    digest = hash_refresh_token(raw_token)
    return session.scalar(select(RefreshToken).where(RefreshToken.token_hash == digest))


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
