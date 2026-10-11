import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.db.models import ROLE_ADMIN, User
from app.db.session import get_db
from app.services.admin_panel import (
    AdminProtected,
    MissingUser,
    agent_files,
    audit_rows,
    list_traces,
    overview,
    rate_limits,
    remove_user,
    search_users,
    set_block,
    trace_detail,
)
from app.services.skill_review import (
    GraphUnavailable,
    SkillClosed,
    SkillMissing,
    UnknownCanonical,
    alias,
    approve,
    list_unknown,
)

_require_admin = require_role(ROLE_ADMIN)

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(_require_admin)],
)


class SkillTarget(BaseModel):
    canonical: str = Field(min_length=1, max_length=80)


@router.get("/overview")
def admin_overview(session: Session = Depends(get_db)) -> dict:
    return overview(session)


@router.get("/users")
def users(q: str = "", session: Session = Depends(get_db)) -> list[dict]:
    return search_users(session, q)


@router.post("/users/{user_id}/block")
def block_user(
    user_id: uuid.UUID,
    admin: User = Depends(_require_admin),
    session: Session = Depends(get_db),
) -> dict:
    return _status(set_user_status(session, admin.id, user_id, True))


@router.post("/users/{user_id}/unblock")
def unblock_user(
    user_id: uuid.UUID,
    admin: User = Depends(_require_admin),
    session: Session = Depends(get_db),
) -> dict:
    return _status(set_user_status(session, admin.id, user_id, False))


@router.delete("/users/{user_id}", status_code=204)
def delete_user(
    user_id: uuid.UUID,
    admin: User = Depends(_require_admin),
    session: Session = Depends(get_db),
) -> None:
    try:
        remove_user(session, admin.id, user_id)
    except MissingUser as exc:
        raise HTTPException(status_code=404, detail="User not found") from exc
    except AdminProtected as exc:
        raise HTTPException(status_code=403, detail="Admins cannot be modified") from exc


@router.get("/traces")
def traces(session: Session = Depends(get_db)) -> list[dict]:
    return list_traces(session)


@router.get("/traces/{run_id}")
def trace(run_id: uuid.UUID, session: Session = Depends(get_db)) -> dict:
    detail = trace_detail(session, run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    return detail


@router.get("/rate-limits")
def limits(session: Session = Depends(get_db)) -> dict:
    return rate_limits(session)


@router.get("/unknown-skills")
def unknown_skills(session: Session = Depends(get_db)) -> list[dict]:
    return [
        {
            "id": row.id,
            "name": row.name,
            "seen_count": row.seen_count,
            "status": row.status,
            "alias_of": row.alias_of,
        }
        for row in list_unknown(session)
    ]


@router.post("/unknown-skills/{skill_id}/approve")
def approve_skill(
    skill_id: uuid.UUID,
    admin: User = Depends(_require_admin),
    session: Session = Depends(get_db),
) -> dict:
    return _skill(lambda: approve(session, admin.id, skill_id))


@router.post("/unknown-skills/{skill_id}/alias")
def alias_skill(
    skill_id: uuid.UUID,
    body: SkillTarget,
    admin: User = Depends(_require_admin),
    session: Session = Depends(get_db),
) -> dict:
    return _skill(lambda: alias(session, admin.id, skill_id, body.canonical.strip(), False))


@router.post("/unknown-skills/{skill_id}/merge")
def merge_skill(
    skill_id: uuid.UUID,
    body: SkillTarget,
    admin: User = Depends(_require_admin),
    session: Session = Depends(get_db),
) -> dict:
    return _skill(lambda: alias(session, admin.id, skill_id, body.canonical.strip(), True))


@router.get("/audit")
def audit(session: Session = Depends(get_db)) -> list[dict]:
    return [
        {
            "id": row.id,
            "admin_id": row.admin_id,
            "user_id": row.user_id,
            "action": row.action,
            "target": row.target,
            "at": row.at,
        }
        for row in audit_rows(session)
    ]


@router.get("/agents")
def agents() -> list[dict]:
    return agent_files()


def set_user_status(session: Session, admin_id: uuid.UUID, user_id: uuid.UUID, blocked: bool) -> User:
    try:
        return set_block(session, admin_id, user_id, blocked)
    except MissingUser as exc:
        raise HTTPException(status_code=404, detail="User not found") from exc
    except AdminProtected as exc:
        raise HTTPException(status_code=403, detail="Admins cannot be modified") from exc


def _status(user: User) -> dict:
    return {"id": user.id, "email": user.email, "role": user.role, "status": user.status}


def _skill(action):
    try:
        row = action()
    except SkillMissing as exc:
        raise HTTPException(status_code=404, detail="Skill not found") from exc
    except SkillClosed as exc:
        raise HTTPException(status_code=409, detail="This skill was already reviewed") from exc
    except UnknownCanonical as exc:
        raise HTTPException(status_code=404, detail="That skill is not in the graph") from exc
    except GraphUnavailable as exc:
        raise HTTPException(status_code=502, detail="Skill graph is unavailable") from exc
    return {"id": row.id, "name": row.name, "status": row.status, "alias_of": row.alias_of}
