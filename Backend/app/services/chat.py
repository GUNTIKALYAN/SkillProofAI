import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.skills_loader import load_skills
from app.config import get_settings
from app.db import ChatMessage, ChatSession, User
from app.guard import check_chat, data_block
from app.llm import LlmError, complete_json
from app.mcp_client import Clients, McpError, call_tool, default_clients, open_tools
from app.schemas.chat import ChatDraft
from app.services.analysis_access import completed_analysis

logger = logging.getLogger(__name__)

_UNKNOWN = "I don't know based on the saved analysis."


class NoAnalysis(Exception):
    pass


class TokenBudget(Exception):
    pass


class ChatFailed(Exception):
    pass


@dataclass
class ChatReply:
    text: str
    before: float | None = None
    after: float | None = None
    skill: str | None = None


def list_messages(session: Session, user_id: uuid.UUID) -> list[ChatMessage]:
    thread = _session_for(session, user_id, None)
    if thread is None:
        return []
    rows = session.scalars(
        select(ChatMessage).where(ChatMessage.session_id == thread.id).order_by(ChatMessage.created_at)
    )
    return list(rows)


def answer(
    session: Session,
    user: User,
    message: str,
    analysis_id: uuid.UUID | None,
    clients: Clients | None = None,
) -> ChatReply:
    settings = get_settings()
    cleaned = check_chat(message, settings.chat_max_chars, str(user.id))
    if _tokens_today(session, user.id) >= settings.chat_daily_tokens:
        raise TokenBudget
    row = completed_analysis(session, user.id, analysis_id)
    if row is None:
        raise NoAnalysis
    thread = _session_for(session, user.id, row.id)
    if thread is None:
        thread = ChatSession(user_id=user.id, analysis_id=row.id)
        session.add(thread)
        session.flush()
    session.add(ChatMessage(session_id=thread.id, role="user", content=cleaned, tokens=0))
    used = clients or default_clients()
    try:
        with open_tools("chatbot", session, used):
            reply, tokens = _reply(cleaned, row.result_json or {})
    except (LlmError, McpError) as exc:
        logger.error("chat failed error=%s", type(exc).__name__)
        raise ChatFailed from exc
    session.add(ChatMessage(session_id=thread.id, role="assistant", content=reply.text, tokens=tokens))
    session.commit()
    return reply


def _reply(message: str, result: dict) -> tuple[ChatReply, int]:
    brief = _brief(result)
    payload: dict = {
        "message": data_block("user_message", message),
        "analysis": brief,
        "tool_results": [],
    }
    limit = load_skills()["chatbot"].limits["max_tool_calls"]
    tokens = 0
    draft = ChatDraft(answer=_UNKNOWN, citations=[])
    learned: dict | None = None
    calls = 0
    while calls <= limit:
        draft, used = complete_json("chatbot", payload, ChatDraft)
        tokens += used
        if draft.tool is None or calls == limit:
            break
        calls += 1
        found = _tool_result(draft.tool.name, draft.tool.skill, result)
        payload["tool_results"].append(found)
        if found.get("tool") == "what_if_learn":
            learned = found
    text = _ground(draft.answer, draft.citations, brief)
    if text == _UNKNOWN or learned is None:
        return ChatReply(text=text), tokens
    return ChatReply(
        text=text,
        before=_number(learned.get("before")),
        after=_number(learned.get("after")),
        skill=_skill_name(learned.get("skill")),
    ), tokens


def _tool_result(name: str, skill: str, result: dict) -> dict:
    if name == "what_if_learn":
        learned = call_tool(
            "what_if_learn",
            {
                "skill": skill,
                "candidate_skills": list(result.get("resume_skills") or []),
                "jd_skills": list(result.get("jd_skills") or []),
            },
            "chatbot",
        )
        return {
            "tool": name,
            "skill": skill,
            "known": learned.get("known"),
            "before": learned.get("before"),
            "after": learned.get("after"),
        }
    found = call_tool(name, {"skill": skill}, "chatbot")
    if name == "related_skills":
        names = [item.get("skill") for item in found.get("related") or [] if isinstance(item, dict)]
        return {"tool": name, "skill": skill, "related": names[:8]}
    return {
        "tool": name,
        "skill": skill,
        "known": found.get("known"),
        "canonical": found.get("canonical"),
    }


def _ground(answer: str, citations: list[str], brief: dict) -> str:
    evidence = _evidence(brief)
    cited = [item for item in citations if item and item.lower() in evidence]
    if cited:
        return answer
    lowered = answer.lower()
    if "don't know" in lowered or "do not know" in lowered:
        return answer
    return _UNKNOWN


def _evidence(brief: dict) -> str:
    parts = [str(brief.get("score"))]
    for item in brief.get("audit") or []:
        parts.append(str(item.get("skill") or ""))
        parts.append(str(item.get("reason") or ""))
    parts.extend(str(skill) for skill in brief.get("plan_skills") or [])
    return " ".join(parts).lower()


def _brief(result: dict) -> dict:
    score = (result.get("jd_match_score") or {}).get("score")
    audit = [
        {"skill": item.get("skill"), "status": item.get("status"), "reason": item.get("reason")}
        for item in (result.get("audit") or [])[:30]
        if isinstance(item, dict)
    ]
    plan = (result.get("action_plan") or {}).get("items") or []
    return {
        "score": score,
        "audit": audit,
        "plan_skills": [item.get("skill") for item in plan if isinstance(item, dict)],
    }


def _session_for(session: Session, user_id: uuid.UUID, analysis_id: uuid.UUID | None) -> ChatSession | None:
    row = session.scalar(
        select(ChatSession).where(ChatSession.user_id == user_id).order_by(ChatSession.created_at.desc())
    )
    if row is not None and analysis_id is not None:
        row.analysis_id = analysis_id
    return row


def _tokens_today(session: Session, user_id: uuid.UUID) -> int:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    total = session.scalar(
        select(func.coalesce(func.sum(ChatMessage.tokens), 0))
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .where(ChatSession.user_id == user_id, ChatMessage.created_at >= start)
    )
    return int(total or 0)


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _skill_name(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    name = value.strip()
    return name or None
