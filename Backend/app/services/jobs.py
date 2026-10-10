import asyncio
import logging
import uuid

import redis
from arq import create_pool
from arq.connections import RedisSettings

from app.config import get_settings

logger = logging.getLogger(__name__)


class QueueError(Exception):
    pass


def enqueue_analysis(analysis_id: uuid.UUID) -> None:
    try:
        asyncio.run(_put(str(analysis_id)))
    except (OSError, redis.RedisError, ConnectionError) as exc:
        logger.error("enqueue failed error=%s", type(exc).__name__)
        raise QueueError("The job queue is unavailable") from exc


async def _put(analysis_id: str) -> None:
    pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    try:
        await pool.enqueue_job("run_analysis", analysis_id)
    finally:
        await pool.close()
