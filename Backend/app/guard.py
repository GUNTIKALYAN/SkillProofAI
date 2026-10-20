import logging
import re

logger = logging.getLogger(__name__)

DOC_MAX_CHARS = 20_000
_PHRASES = (
    "ignore previous instructions",
    "ignore all previous",
    "reveal your system prompt",
    "reveal the system prompt",
    "act as",
)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class GuardRefusal(Exception):
    def __init__(self) -> None:
        super().__init__("That message was refused.")


def check_chat(message: str, max_chars: int, user_id: str) -> str:
    cleaned = strip_controls(message)
    if len(cleaned) > max_chars:
        raise ValueError("Message is too long")
    if not cleaned.strip():
        raise ValueError("Message is empty")
    lowered = cleaned.lower()
    for phrase in _PHRASES:
        if phrase in lowered:
            logger.warning("prompt injection refused user_id=%s", user_id)
            raise GuardRefusal
    return cleaned


def guard_document(label: str, text: str, limit: int = DOC_MAX_CHARS) -> str:
    cleaned = strip_controls(text)
    if len(cleaned) > limit:
        logger.info("text clipped source=%s chars=%s", label, len(cleaned))
        cleaned = cleaned[:limit]
    return data_block(label, cleaned)


def data_block(label: str, text: str) -> str:
    tag = _tag(label)
    return f"<{tag}>\n{text}\n</{tag}>"


def strip_controls(text: str) -> str:
    return _CONTROL.sub("", text)


def _tag(label: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in label.strip().lower())
    tag = cleaned.strip("_")
    return tag or "data"
