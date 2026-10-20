from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import UnknownSkill, utc_now

_MAX_NAME = 80


def save_unknown_skills(session: Session, names: list[str]) -> None:
    for name in sorted(set(names)):
        if not name or len(name) > _MAX_NAME:
            continue
        row = session.scalar(select(UnknownSkill).where(UnknownSkill.name == name))
        if row is None:
            session.add(UnknownSkill(name=name))
            continue
        row.seen_count += 1
        row.updated_at = utc_now()
