import json
import logging
from datetime import datetime, timezone
from pathlib import Path

_LOG_DIR = Path(__file__).resolve().parents[1] / ".logs"
_FILES = ("backend-logs", "mcp-logs", "worker-logs")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


class _McpFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.name.startswith("app.mcp_client") or record.name.startswith("app.services.bucket")


def configure_logging(role: str = "backend") -> None:
    formatter = JsonFormatter()
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    root.setLevel(logging.INFO)
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    root.addHandler(stream)
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    for name in _FILES:
        try:
            (_LOG_DIR / name).touch(exist_ok=True)
        except OSError:
            return
    chosen = "worker-logs" if role == "worker" else "backend-logs"
    _attach(root, _LOG_DIR / chosen, formatter, None)
    _attach(root, _LOG_DIR / "mcp-logs", formatter, _McpFilter())


def _attach(root: logging.Logger, path: Path, formatter: logging.Formatter, log_filter: logging.Filter | None) -> None:
    try:
        handler = logging.FileHandler(path, encoding="utf-8")
    except OSError:
        return
    handler.setFormatter(formatter)
    if log_filter is not None:
        handler.addFilter(log_filter)
    root.addHandler(handler)
