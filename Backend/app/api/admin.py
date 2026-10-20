import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import User, get_db
from app.security import require_admin
from app.services.admin_panel import (
    AdminProtected,
    MissingUser,
    agent_files,
    list_traces,
    overview,
    remove_user,
    search_users,
    set_block,
    trace_detail,
)

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


@router.get("/overview")
def admin_overview(session: Session = Depends(get_db)) -> dict:
    return overview(session)


@router.get("/users")
def users(q: str = "", session: Session = Depends(get_db)) -> list[dict]:
    return search_users(session, q)


@router.post("/users/{user_id}/block")
def block_user(
    user_id: uuid.UUID,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_db),
) -> dict:
    return _status(set_user_status(session, admin.id, user_id, True))


@router.post("/users/{user_id}/unblock")
def unblock_user(
    user_id: uuid.UUID,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_db),
) -> dict:
    return _status(set_user_status(session, admin.id, user_id, False))


@router.delete("/users/{user_id}", status_code=204)
def delete_user(
    user_id: uuid.UUID,
    admin: User = Depends(require_admin),
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
