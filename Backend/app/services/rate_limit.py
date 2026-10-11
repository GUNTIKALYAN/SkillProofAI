import math
import threading
import time
import uuid

import redis

LIMITS = {
    "auth": (5, 60),
    "analyze": (5, 60 * 60),
    "chat": (20, 60),
}

_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  local retry = 1
  if oldest[2] ~= nil then
    retry = math.ceil((tonumber(oldest[2]) + window - now) / 1000)
    if retry < 1 then
      retry = 1
    end
  end
  return {0, retry}
end
redis.call('ZADD', key, now, member)
redis.call('PEXPIRE', key, window)
return {1, 0}
"""


class RateLimitError(Exception):
    pass


class MemoryLimiter:
    def __init__(
        self,
        hits: dict[str, list[float]] | None = None,
        lock: threading.Lock | None = None,
    ) -> None:
        self._hits = {} if hits is None else hits
        self._lock = threading.Lock() if lock is None else lock

    def take(self, endpoint: str, identity: str, now: float | None = None) -> int | None:
        limit, window = LIMITS[endpoint]
        moment = time.time() if now is None else now
        key = f"{endpoint}:{identity}"
        with self._lock:
            stamps = [item for item in self._hits.get(key, []) if item > moment - window]
            if len(stamps) >= limit:
                self._hits[key] = stamps
                retry = math.ceil(stamps[0] + window - moment)
                return max(int(retry), 1)
            stamps.append(moment)
            self._hits[key] = stamps
            return None


class RedisLimiter:
    def __init__(self, url: str) -> None:
        self._redis = redis.Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2)
        self._script = self._redis.register_script(_SCRIPT)

    def take(self, endpoint: str, identity: str, now: float | None = None) -> int | None:
        limit, window = LIMITS[endpoint]
        moment = time.time() if now is None else now
        key = f"rl:{endpoint}:{identity}"
        member = f"{int(moment * 1000)}:{uuid.uuid4()}"
        try:
            allowed, retry = self._script(
                keys=[key],
                args=[int(moment * 1000), window * 1000, limit, member],
            )
        except redis.RedisError as exc:
            raise RateLimitError("redis unavailable") from exc
        if int(allowed) == 1:
            return None
        return max(int(retry), 1)


_limiter: MemoryLimiter | RedisLimiter | None = None


def get_limiter() -> MemoryLimiter | RedisLimiter:
    global _limiter
    if _limiter is None:
        from app.config import get_settings

        _limiter = RedisLimiter(get_settings().redis_url)
    return _limiter


def set_limiter(limiter: MemoryLimiter | RedisLimiter | None) -> None:
    global _limiter
    _limiter = limiter
