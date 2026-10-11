import logging
import threading

import redis

from app.config import get_settings

logger = logging.getLogger(__name__)

QUEUE_KEY = "arq:queue"
_METRICS_KEY = "metrics:skillproof"


class MemoryRecorder:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.http_count = 0
        self.http_ms = 0
        self.llm_count = 0
        self.llm_ms = 0

    def observe_http(self, latency_ms: int) -> None:
        with self._lock:
            self.http_count += 1
            self.http_ms += max(latency_ms, 0)

    def observe_llm(self, latency_ms: int) -> None:
        with self._lock:
            self.llm_count += 1
            self.llm_ms += max(latency_ms, 0)

    def render(self) -> str:
        with self._lock:
            return _format(self.http_count, self.http_ms, self.llm_count, self.llm_ms, 0)


class RedisRecorder:
    def __init__(self, url: str) -> None:
        self._redis = redis.Redis.from_url(url, socket_timeout=1, socket_connect_timeout=1)
        self._local = MemoryRecorder()

    def observe_http(self, latency_ms: int) -> None:
        self._bump("http", latency_ms)

    def observe_llm(self, latency_ms: int) -> None:
        self._bump("llm", latency_ms)

    def render(self) -> str:
        try:
            raw = self._redis.hgetall(_METRICS_KEY)
            depth = int(self._redis.zcard(QUEUE_KEY))
        except redis.RedisError:
            logger.warning("metrics read failed")
            return self._local.render()
        counts = {key.decode(): int(value) for key, value in raw.items()}
        return _format(
            counts.get("http_count", 0),
            counts.get("http_ms", 0),
            counts.get("llm_count", 0),
            counts.get("llm_ms", 0),
            depth,
        )

    def _bump(self, kind: str, latency_ms: int) -> None:
        try:
            pipe = self._redis.pipeline()
            pipe.hincrby(_METRICS_KEY, f"{kind}_count", 1)
            pipe.hincrby(_METRICS_KEY, f"{kind}_ms", max(latency_ms, 0))
            pipe.execute()
        except redis.RedisError:
            logger.warning("metrics write failed")
            if kind == "http":
                self._local.observe_http(latency_ms)
            else:
                self._local.observe_llm(latency_ms)


Recorder = MemoryRecorder | RedisRecorder
_recorder: Recorder | None = None


def get_recorder() -> Recorder:
    global _recorder
    if _recorder is None:
        _recorder = RedisRecorder(get_settings().redis_url)
    return _recorder


def set_recorder(recorder: Recorder | None) -> None:
    global _recorder
    _recorder = recorder


def observe_http(latency_ms: int) -> None:
    get_recorder().observe_http(latency_ms)


def observe_llm(latency_ms: int) -> None:
    get_recorder().observe_llm(latency_ms)


def render_metrics() -> str:
    return get_recorder().render()


def _format(http_count: int, http_ms: int, llm_count: int, llm_ms: int, queue_depth: int) -> str:
    lines = [
        "# HELP skillproof_http_requests_total HTTP requests served.",
        "# TYPE skillproof_http_requests_total counter",
        f"skillproof_http_requests_total {http_count}",
        "# HELP skillproof_http_latency_ms_sum Total HTTP request latency in milliseconds.",
        "# TYPE skillproof_http_latency_ms_sum counter",
        f"skillproof_http_latency_ms_sum {http_ms}",
        "# HELP skillproof_llm_requests_total LLM calls.",
        "# TYPE skillproof_llm_requests_total counter",
        f"skillproof_llm_requests_total {llm_count}",
        "# HELP skillproof_llm_latency_ms_sum Total LLM latency in milliseconds.",
        "# TYPE skillproof_llm_latency_ms_sum counter",
        f"skillproof_llm_latency_ms_sum {llm_ms}",
        "# HELP skillproof_queue_depth Analysis jobs waiting in Redis.",
        "# TYPE skillproof_queue_depth gauge",
        f"skillproof_queue_depth {queue_depth}",
    ]
    return "\n".join(lines) + "\n"
