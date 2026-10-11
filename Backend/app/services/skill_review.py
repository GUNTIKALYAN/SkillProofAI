import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLog, UnknownSkill, utc_now
from app.mcp_client.graph_admin import GraphAdminError, add_alias, add_skill


class SkillMissing(Exception):
    pass


class SkillClosed(Exception):
    pass


class GraphUnavailable(Exception):
    pass


class UnknownCanonical(Exception):
    pass


def list_unknown(session: Session) -> list[UnknownSkill]:
    rows = session.scalars(select(UnknownSkill).order_by(UnknownSkill.seen_count.desc()))
    return list(rows)


def approve(session: Session, admin_id: uuid.UUID, skill_id: uuid.UUID) -> UnknownSkill:
    row = _pending(session, skill_id)
    try:
        added = add_skill(row.name)
    except GraphAdminError as exc:
        raise GraphUnavailable from exc
    if not added:
        raise UnknownCanonical
    row.status = "approved"
    row.alias_of = None
    row.updated_at = utc_now()
    _audit(session, admin_id, "approve_skill", row.name)
    session.commit()
    return row


def alias(session: Session, admin_id: uuid.UUID, skill_id: uuid.UUID, canonical: str, merged: bool) -> UnknownSkill:
    row = _pending(session, skill_id)
    try:
        linked = add_alias(row.name, canonical)
    except GraphAdminError as exc:
        raise GraphUnavailable from exc
    if not linked:
        raise UnknownCanonical
    row.status = "merged" if merged else "aliased"
    row.alias_of = canonical
    row.updated_at = utc_now()
    _audit(session, admin_id, "merge_skill" if merged else "alias_skill", row.name)
    session.commit()
    return row


def _pending(session: Session, skill_id: uuid.UUID) -> UnknownSkill:
    row = session.get(UnknownSkill, skill_id)
    if row is None:
        raise SkillMissing
    if row.status != "pending":
        raise SkillClosed
    return row


def _audit(session: Session, admin_id: uuid.UUID, action: str, target: str) -> None:
    session.add(AuditLog(admin_id=admin_id, action=action, target=target))
