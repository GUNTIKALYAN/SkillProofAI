import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import ROLE_ADMIN, User
from app.security import hash_password

logger = logging.getLogger(__name__)

MIN_PASSWORD_LENGTH = 8


class AdminSeedError(Exception):
    pass


def seed_admin(session: Session, email: str, password: str) -> str:
    normalized = email.strip().lower()
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AdminSeedError("ADMIN_PASSWORD must be at least 8 characters")
    existing = session.scalar(select(User).where(User.email == normalized))
    if existing is not None:
        if existing.role != ROLE_ADMIN:
            raise AdminSeedError("That email is already registered and is not an admin")
        logger.info("admin already exists")
        return "exists"
    try:
        password_hash = hash_password(password)
    except ValueError as exc:
        raise AdminSeedError(str(exc)) from exc
    session.add(
        User(
            email=normalized,
            password_hash=password_hash,
            role=ROLE_ADMIN,
        )
    )
    session.commit()
    logger.info("admin created")
    return "created"
