import uuid
from collections.abc import Callable

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db.models import STATUS_ACTIVE, User
from app.db.session import get_db
from app.services.tokens import TokenError, decode_access_token


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


def require_role(role: str) -> Callable:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role != role:
            raise HTTPException(status_code=403, detail="Not allowed")
        return user

    return dependency


def _bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Not authenticated")
    return token.strip()
