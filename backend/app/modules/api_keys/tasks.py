"""Celery task that flushes API-key ``last_used_at`` timestamps (FIX 21).

Authentication no longer writes ``UPDATE api_keys SET last_used_at`` on every
request — that write amplified every API-key-authenticated call into a write
transaction on the hot path. Instead ``authenticate_key`` records the
timestamp in Redis (``apikey:last_used:<id>``, 5-minute TTL) and this beat
task drains those keys back into PostgreSQL every 5 minutes.
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.infrastructure.async_tasks import async_task_body
from app.infrastructure.celery_app import celery_app

logger = logging.getLogger(__name__)

LAST_USED_KEY_PREFIX = "apikey:last_used"
FLUSH_BATCH_SIZE = 500


async def _drain_last_used_redis() -> dict[str, str]:
    """Return ``{api_key_id: iso_timestamp}`` for all pending Redis entries."""
    from app.infrastructure.redis_client import get_redis

    redis = get_redis()
    mapping: dict[str, str] = {}
    try:
        async for key in redis.scan_iter(
            match=f"{LAST_USED_KEY_PREFIX}:*", count=200
        ):
            if len(mapping) >= FLUSH_BATCH_SIZE:
                break
            api_key_id = key.rsplit(":", 1)[-1]
            value = await redis.get(key)
            if value:
                mapping[api_key_id] = value
    except Exception as exc:
        logger.warning("Could not read api key last_used Redis keys: %s", exc)
    return mapping


async def _clear_redis_keys(api_key_ids: list[str]) -> None:
    if not api_key_ids:
        return
    try:
        from app.infrastructure.redis_client import get_redis

        redis = get_redis()
        keys = [f"{LAST_USED_KEY_PREFIX}:{key_id}" for key_id in api_key_ids]
        await redis.delete(*keys)
    except Exception as exc:
        logger.warning("Could not clear api key last_used Redis keys: %s", exc)


@celery_app.task(name="app.modules.api_keys.tasks.flush_api_key_last_used")
def flush_api_key_last_used() -> int:
    """Move pending ``last_used_at`` timestamps from Redis into PostgreSQL."""

    async def _run(session) -> int:
        import uuid as uuid_mod

        from app.modules.api_keys.repository import ApiKeyRepository

        mapping = await _drain_last_used_redis()
        if not mapping:
            return 0

        parsed: dict[uuid_mod.UUID, datetime] = {}
        for api_key_id, iso_value in mapping.items():
            try:
                parsed[uuid_mod.UUID(api_key_id)] = datetime.fromisoformat(
                    iso_value.replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                logger.debug("Ignoring malformed last_used entry for %s", api_key_id)

        updated = 0
        if parsed:
            try:
                updated = await ApiKeyRepository.update_last_used_batch(
                    session, parsed
                )
            except Exception:
                logger.exception("Failed to flush API key last_used timestamps")
                raise

        await _clear_redis_keys(list(mapping.keys()))
        if updated:
            logger.info("Flushed last_used_at for %s API keys", updated)
        return updated

    return async_task_body(_run)
