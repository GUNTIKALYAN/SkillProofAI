import logging

import redis
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.db.session import get_engine
from app.mcp_client.transport import skillgraph_ready

logger = logging.getLogger(__name__)


def checks() -> dict[str, bool]:
    return {
        "postgres": postgres_ok(),
        "redis": redis_ok(),
        "neo4j": neo4j_ok(),
    }


def postgres_ok() -> bool:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.error("postgres check failed error=%s", type(exc).__name__)
        return False
    return True


def redis_ok() -> bool:
    client = redis.Redis.from_url(
        get_settings().redis_url,
        socket_timeout=2,
        socket_connect_timeout=2,
    )
    try:
        return bool(client.ping())
    except redis.RedisError as exc:
        logger.error("redis check failed error=%s", type(exc).__name__)
        return False


def neo4j_ok() -> bool:
    return skillgraph_ready(get_settings().skillgraph_url)
