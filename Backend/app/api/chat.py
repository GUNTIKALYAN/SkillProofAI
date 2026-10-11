import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.limits import limit_chat
from app.config import get_settings
from app.db.models import User
from app.db.session import get_db
from app.schemas.chat import ChatMessagePublic, ChatRequest
from app.services.chat import ChatFailed, NoAnalysis, TokenBudget, answer, list_messages

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("", response_model=list[ChatMessagePublic])
def messages(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list:
    return list_messages(session, user.id)


@router.post("")
def send_message(
    body: ChatRequest,
    user: User = Depends(limit_chat),
    session: Session = Depends(get_db),
) -> StreamingResponse:
    if len(body.message) > get_settings().chat_max_chars:
        raise HTTPException(status_code=422, detail="Message is too long")
    try:
        reply = answer(session, user, body.message, body.analysis_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TokenBudget as exc:
        raise HTTPException(status_code=429, detail="Daily token budget is used up") from exc
    except NoAnalysis as exc:
        raise HTTPException(status_code=400, detail="Run an analysis before chatting") from exc
    except ChatFailed as exc:
        raise HTTPException(status_code=502, detail="The chat reply failed") from exc
    return StreamingResponse(_events(reply.text, reply.before, reply.after, reply.skill), media_type="text/event-stream")


def _events(text: str, before: float | None, after: float | None, skill: str | None):
    for start in range(0, len(text), 48):
        yield _event({"text": text[start : start + 48]})
    if before is not None and after is not None:
        yield _event({"skill": skill, "before": before, "after": after})
    yield _event({"done": True})


def _event(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"
