from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.db.models import ROLE_ADMIN, User
from app.db.session import get_db
from app.schemas.auth import UserPublic
from app.services.users import list_users

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_role(ROLE_ADMIN))],
)


@router.get("/users", response_model=list[UserPublic])
def users(session: Session = Depends(get_db)) -> list[User]:
    return list_users(session)
