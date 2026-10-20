"""Check the Groq key in .env. From the project root: python check_llm.py"""

import logging
from pathlib import Path

from groq import APIError, Groq

logger = logging.getLogger("check_llm")


def _env(name: str) -> str:
    path = Path(__file__).resolve().parent / ".env"
    if not path.is_file():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == name:
            return value.strip().strip('"').strip("'")
    return ""


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    key = _env("GROQ_API_KEY")
    model = _env("LLAMA_MODEL") or "openai/gpt-oss-20b"
    if not key:
        logger.error("GROQ_API_KEY is missing from .env")
        return 1
    client = Groq(api_key=key, timeout=60)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Reply with a JSON object."},
                {"role": "user", "content": 'Return {"ok": true}'},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
    except APIError as exc:
        status = getattr(exc, "status_code", None)
        detail = getattr(exc, "message", None) or str(exc).split("\n", 1)[0]
        logger.error("key check failed status=%s model=%s detail=%s", status, model, detail[:300])
        return 1
    content = (response.choices[0].message.content or "")[:200]
    logger.info("key accepted model=%s reply=%s", model, content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
