import logging

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import get_settings
from app.db.models import User
from app.db.session import get_db
from app.schemas.auth import LoginRequest, SignupRequest, TokenResponse, UserPublic
from app.services.auth_service import (
    EmailTaken,
    InvalidCredentials,
    login_user,
    refresh_session,
    register_user,
    revoke_refresh_token,
)
from app.services.tokens import (
    REFRESH_COOKIE,
    REFRESH_COOKIE_PATH,
    access_token_ttl_seconds,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", status_code=201, response_model=TokenResponse)
def signup(
    body: SignupRequest,
    response: Response,
    session: Session = Depends(get_db),
) -> TokenResponse:
    try:
        issued = register_user(session, body.normalized_email(), body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EmailTaken as exc:
        logger.warning("signup rejected")
        raise HTTPException(status_code=409, detail="Email is already registered") from exc
    _set_refresh_cookie(response, issued.refresh_token)
    return _token_response(issued.access_token)


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    response: Response,
    session: Session = Depends(get_db),
) -> TokenResponse:
    try:
        issued = login_user(session, body.normalized_email(), body.password)
    except InvalidCredentials as exc:
        logger.warning("login failed")
        raise HTTPException(status_code=401, detail="Invalid email or password") from exc
    _set_refresh_cookie(response, issued.refresh_token)
    return _token_response(issued.access_token)


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    response: Response,
    session: Session = Depends(get_db),
    refresh_token: str | None = Cookie(default=None),
) -> TokenResponse:
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        issued = refresh_session(session, refresh_token)
    except InvalidCredentials as exc:
        logger.warning("refresh rejected")
        raise HTTPException(status_code=401, detail="Not authenticated") from exc
    _set_refresh_cookie(response, issued.refresh_token)
    return _token_response(issued.access_token)


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    session: Session = Depends(get_db),
    refresh_token: str | None = Cookie(default=None),
) -> None:
    if refresh_token:
        revoke_refresh_token(session, refresh_token)
    _clear_refresh_cookie(response)


@router.get("/me", response_model=UserPublic)
def me(user: User = Depends(get_current_user)) -> User:
    return user


def _token_response(access_token: str) -> TokenResponse:
    return TokenResponse(access_token=access_token, expires_in=access_token_ttl_seconds())


def _set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.refresh_token_days * 24 * 60 * 60,
        path=REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=REFRESH_COOKIE,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
