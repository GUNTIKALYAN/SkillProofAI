import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from jwt.exceptions import PyJWTError

from app.config import get_settings

ACCESS_ALGORITHM = "HS256"
REFRESH_COOKIE = "refresh_token"
REFRESH_COOKIE_PATH = "/api/auth"


class TokenError(Exception):
    pass


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
    days = get_settings().refresh_token_days
    return datetime.now(timezone.utc) + timedelta(days=days)
