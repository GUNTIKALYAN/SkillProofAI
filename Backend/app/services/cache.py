import json
import threading

import redis


class CacheError(Exception):
    pass


class MemoryCache:
    def __init__(self) -> None:
        self._values: dict[str, dict] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> dict | None:
        with self._lock:
            value = self._values.get(key)
            return None if value is None else dict(value)

    def set(self, key: str, value: dict, ttl: int) -> None:
        del ttl
        with self._lock:
            self._values[key] = dict(value)


class RedisCache:
    def __init__(self, url: str) -> None:
        self._redis = redis.Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2)

    def get(self, key: str) -> dict | None:
        try:
            raw = self._redis.get(key)
        except redis.RedisError as exc:
            raise CacheError from exc
        if not isinstance(raw, (bytes, str)):
            return None
        loaded = json.loads(raw)
        if isinstance(loaded, dict):
            return loaded
        return None

    def set(self, key: str, value: dict, ttl: int) -> None:
        try:
            self._redis.set(key, json.dumps(value), ex=ttl)
        except redis.RedisError as exc:
            raise CacheError from exc
