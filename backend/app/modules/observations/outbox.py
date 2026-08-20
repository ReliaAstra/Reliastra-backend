"""Repository + processing logic for the observation outbox (FIX 9).

The outbox guarantees at-least-once delivery of observations to the immutable
evidence stream: events are committed atomically with the check result that
produced them, and this module drains them into ``observations`` afterwards.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.observations.models import OutboxEvent
from app.modules.observations.schemas import ObservationCreateDTO
from app.modules.observations.service import observation_service

logger = logging.getLogger(__name__)

PROCESS_BATCH_SIZE = 100


class OutboxRepository:
    @staticmethod
    async def list_pending(
        session: AsyncSession, limit: int = PROCESS_BATCH_SIZE
    ) -> list[OutboxEvent]:
        """Return the oldest pending events, locking them against concurrent
        processors (SKIP LOCKED keeps multiple workers from re-processing)."""
        query = (
            select(OutboxEvent)
            .order_by(OutboxEvent.created_at.asc(), OutboxEvent.id.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def delete(session: AsyncSession, event: OutboxEvent) -> None:
        await session.execute(delete(OutboxEvent).where(OutboxEvent.id == event.id))


async def process_outbox_batch(
    session: AsyncSession, limit: int = PROCESS_BATCH_SIZE
) -> int:
    """Drain up to *limit* pending outbox events into ``observations``.

    Each event is deleted in the same transaction that records its
    observation, so a crash can never lose an observation (the event row
    stays pending) or duplicate one (delete + insert commit together).
    """
    events = await OutboxRepository.list_pending(session, limit=limit)
    processed = 0
    for event in events:
        if event.event_type != "observation_created":
            logger.warning(
                "Skipping unknown outbox event type %s (id=%s)",
                event.event_type,
                event.id,
            )
            await OutboxRepository.delete(session, event)
            continue
        try:
            dto = ObservationCreateDTO.model_validate_json(event.payload)
            await observation_service.record_observation(session, dto)
            await OutboxRepository.delete(session, event)
            processed += 1
        except Exception:
            logger.exception("Failed to process outbox event %s", event.id)
            # Leave the event pending for the next cycle; do not lose data.
    if processed:
        logger.info("Outbox processor recorded %s observations", processed)
    return processed
