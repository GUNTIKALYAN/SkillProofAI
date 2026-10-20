import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException
from jwt.exceptions import PyJWTError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import ROLE_ADMIN, ROLE_USER, STATUS_ACTIVE, RefreshToken, User, get_db

ACCESS_ALGORITHM = "HS256"
REFRESH_COOKIE = "refresh_token"
REFRESH_COOKIE_PATH = "/api/auth"
_BCRYPT_MAX_BYTES = 72


class TokenError(Exception):
    pass


class InvalidCredentials(Exception):
    pass


class EmailTaken(Exception):
    pass


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    refresh_token: str


def hash_password(password: str) -> str:
    if len(password.encode("utf-8")) > _BCRYPT_MAX_BYTES:
        raise ValueError("Password must be 72 bytes or fewer")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if len(password.encode("utf-8")) > _BCRYPT_MAX_BYTES:
        return False
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def access_token_ttl_seconds() -> int:
    return get_settings().access_token_minutes * 60


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ACCESS_ALGORITHM)


def decode_access_token(token: str) -> dict[str, object]:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ACCESS_ALGORITHM])
    except PyJWTError as exc:
        raise TokenError from exc
    if "sub" not in payload or "role" not in payload:
        raise TokenError
    return payload


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def refresh_expires_at() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=get_settings().refresh_token_days)


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


def get_current_user(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_db),
) -> User:
    token = _bearer_token(authorization)
    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(str(payload["sub"]))
    except (TokenError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Not authenticated") from exc
    user = session.get(User, user_id)
    if user is None or user.status != STATUS_ACTIVE:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Not allowed")
    return user


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


def _bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Not authenticated")
    return token.strip()
