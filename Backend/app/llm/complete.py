import json
import logging
import random
import time
from collections.abc import Callable

from groq import APIError
from pydantic import BaseModel, ValidationError

from app.agents.skills.loader import SkillError, load_skills
from app.config import get_settings
from app.mcp_client.context import get_llm
from app.services.metrics import observe_llm

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
_NO_RETRY = {400, 401, 403, 404}


class LlmError(Exception):
    pass


class LlmStatus(Exception):
    def __init__(self, status: int) -> None:
        self.status = status
        super().__init__(f"status {status}")


def complete_json(
    node: str,
    payload: dict,
    schema: type[BaseModel],
    check: Callable[[BaseModel], None] | None = None,
) -> tuple[BaseModel, int]:
    try:
        system = load_skills()[node].body
    except (KeyError, SkillError) as exc:
        raise LlmError("Skill file is missing") from exc
    caller = get_llm() or _groq
    feedback = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        user = json.dumps(payload)
        if feedback:
            user = f"{user}\n\nValidation error: {feedback}"
        try:
            started = time.perf_counter()
            try:
                raw, tokens = caller(system, user)
            finally:
                observe_llm(max(int((time.perf_counter() - started) * 1000), 0))
            if not isinstance(raw, dict):
                raise json.JSONDecodeError("expected object", "", 0)
            model = schema.model_validate(raw)
            if check is not None:
                check(model)
            return model, int(tokens)
        except LlmStatus as exc:
            logger.error("llm failed node=%s status=%s", node, exc.status)
            if exc.status in _NO_RETRY or attempt == MAX_ATTEMPTS:
                raise LlmError("The model request was rejected") from exc
            _sleep(_delay(attempt))
        except (ValidationError, json.JSONDecodeError, ValueError) as exc:
            feedback = _feedback(exc)
            logger.error("llm invalid node=%s attempt=%s error=%s", node, attempt, type(exc).__name__)
            if attempt == MAX_ATTEMPTS:
                raise LlmError("The model returned invalid JSON") from exc
            _sleep(_delay(attempt))
    raise LlmError("The model returned invalid JSON")


def _groq(system: str, user: str) -> tuple[dict, int]:
    from groq import Groq

    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key, timeout=60)
    try:
        response = client.chat.completions.create(
            model=settings.llama_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
    except APIError as exc:
        status = getattr(exc, "status_code", None)
        raise LlmStatus(int(status) if isinstance(status, int) else 504) from exc
    content = response.choices[0].message.content or ""
    usage = response.usage
    tokens = int(usage.total_tokens) if usage is not None and usage.total_tokens else 0
    logger.info("llm response received model=%s tokens=%s", settings.llama_model, tokens)
    return json.loads(content), tokens


def _feedback(exc: Exception) -> str:
    if isinstance(exc, ValidationError) and exc.errors():
        err = exc.errors()[0]
        loc = ".".join(str(part) for part in err.get("loc", ()))
        return f"{loc}: {err.get('msg', 'invalid')}"[:200]
    return str(exc).split("\n", 1)[0][:200]


def _delay(attempt: int) -> float:
    return 0.5 * (2 ** (attempt - 1)) + random.uniform(0, 0.1)


def _sleep(seconds: float) -> None:
    time.sleep(seconds)
