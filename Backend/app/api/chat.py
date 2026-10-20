from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import User, get_db
from app.guard import GuardRefusal
from app.schemas.chat import ChatMessagePublic, ChatReplyPublic, ChatRequest
from app.security import get_current_user
from app.services.analysis_access import NotFound
from app.services.chat import ChatFailed, NoAnalysis, TokenBudget, answer, list_messages

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("", response_model=list[ChatMessagePublic])
def messages(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list:
    return list_messages(session, user.id)


@router.post("", response_model=ChatReplyPublic)
def send_message(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> ChatReplyPublic:
    try:
        reply = answer(session, user, body.message, body.analysis_id)
    except GuardRefusal as exc:
        raise HTTPException(status_code=400, detail="That message was refused.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TokenBudget as exc:
        raise HTTPException(status_code=429, detail="Daily token budget is used up") from exc
    except NotFound as exc:
        raise HTTPException(status_code=404, detail="Analysis not found") from exc
    except NoAnalysis as exc:
        raise HTTPException(status_code=400, detail="Run an analysis before chatting") from exc
    except ChatFailed as exc:
        raise HTTPException(status_code=502, detail="The chat reply failed") from exc
    return ChatReplyPublic(text=reply.text, before=reply.before, after=reply.after, skill=reply.skill)
