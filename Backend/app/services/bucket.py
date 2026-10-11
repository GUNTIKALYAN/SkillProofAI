import threading

import redis

BUCKET_LIMITS = {
    "skillgraph": 60,
    "github": 20,
    "tavily": 10,
    "verify": 10,
}
_DEFAULT_LIMIT = 10
_WINDOW_SECONDS = 60


class BucketError(Exception):
    pass


class MemoryBucket:
    def __init__(self, limits: dict[str, int] | None = None) -> None:
        self._limits = dict(BUCKET_LIMITS if limits is None else limits)
        self._used: dict[str, int] = {}
        self._lock = threading.Lock()

    def take(self, server: str) -> bool:
        limit = self._limits.get(server, _DEFAULT_LIMIT)
        with self._lock:
            used = self._used.get(server, 0)
            if used >= limit:
                return False
            self._used[server] = used + 1
            return True


class RedisBucket:
    def __init__(self, url: str, client: object | None = None) -> None:
        if client is None:
            self._redis = redis.Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2)
        else:
            self._redis = client

    def take(self, server: str) -> bool:
        limit = BUCKET_LIMITS.get(server, _DEFAULT_LIMIT)
        key = f"mcp:bucket:{server}"
        try:
            count = int(self._redis.incr(key))
            if count == 1:
                self._redis.expire(key, _WINDOW_SECONDS)
        except redis.RedisError as exc:
            raise BucketError("redis unavailable") from exc
        return count <= limit
