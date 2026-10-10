from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User


def list_users(session: Session) -> list[User]:
    return list(session.scalars(select(User).order_by(User.created_at)))
