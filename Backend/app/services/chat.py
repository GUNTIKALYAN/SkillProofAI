import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.skills_loader import load_skills
from app.config import get_settings
from app.db import ChatMessage, ChatSession, User
from app.llm.complete import LlmError, complete_json
from app.mcp_client import Clients, McpError, call_tool, default_clients, open_tools

logger = logging.getLogger(__name__)

_WHAT_IF = re.compile(r"what if i learn\s+([A-Za-z0-9][A-Za-z0-9 .+#-]{0,78})", re.IGNORECASE)
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
    if len(message) > settings.chat_max_chars:
        raise ValueError("Message is too long")
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
    session.add(ChatMessage(session_id=thread.id, role="user", content=message, tokens=0))
    used = clients or default_clients()
    try:
        with open_tools("chatbot", session, used):
            reply, tokens = _reply(message, row.result_json or {})
    except (LlmError, McpError) as exc:
        logger.error("chat failed error=%s", type(exc).__name__)
        raise ChatFailed from exc
    session.add(ChatMessage(session_id=thread.id, role="assistant", content=reply.text, tokens=tokens))
    session.commit()
    return reply


def _reply(message: str, result: dict) -> tuple[ChatReply, int]:
    skill = _what_if_skill(message)
    if skill:
        return _what_if(skill, result), 0
    return _talk(message, result)


def _what_if(skill: str, result: dict) -> ChatReply:
    learned = call_tool(
        "what_if_learn",
        {
            "skill": skill,
            "candidate_skills": list(result.get("resume_skills") or []),
            "jd_skills": list(result.get("jd_skills") or []),
        },
        "chatbot",
    )
    before = float(learned.get("before") or 0)
    after = float(learned.get("after") or 0)
    name = str(learned.get("skill") or skill)
    if not learned.get("known"):
        text = f"I don't know {name} in the skill graph, so I can't show a new score."
    else:
        text = (
            f"If you learn {name}, the JD Match Score moves from {_percent(before)} to {_percent(after)}. "
            "This uses your saved analysis and the skill graph."
        )
    return ChatReply(text=text, before=before, after=after, skill=name)


def _talk(message: str, result: dict) -> tuple[ChatReply, int]:
    brief = _brief(result)
    payload: dict = {"message": message, "analysis": brief, "tool_results": []}
    limit = load_skills()["chatbot"].limits["max_tool_calls"]
    tokens = 0
    draft = ChatDraft(answer=_UNKNOWN, citations=[])
    calls = 0
    while calls <= limit:
        draft, used = complete_json("chatbot", payload, ChatDraft)
        tokens += used
        if draft.tool is None or calls == limit:
            break
        calls += 1
        payload["tool_results"].append(_tool_result(draft.tool.name, draft.tool.skill, result))
    text = _ground(draft.answer, draft.citations, brief)
    return ChatReply(text=text), tokens


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


def _what_if_skill(message: str) -> str | None:
    match = _WHAT_IF.search(message.strip())
    if match is None:
        return None
    skill = match.group(1).strip(" .!?")
    return skill or None


def _percent(score: float) -> str:
    if score <= 1:
        return f"{round(score * 100)}%"
    return str(round(score))
