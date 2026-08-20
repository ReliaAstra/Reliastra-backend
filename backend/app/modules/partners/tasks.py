"""Celery tasks for the Partner Referral program (v1).

Only what is actually necessary: a single idempotent job that promotes
commissions whose hold period has elapsed from ``pending`` to ``payable``.
Commission creation itself is event-driven — it happens inside the billing
webhook when a payment is confirmed.
"""

from __future__ import annotations

import logging

from app.db.session import get_session_maker
from app.infrastructure.celery_app import celery_app
from app.modules.partners.commissions import commission_service

logger = logging.getLogger(__name__)


@celery_app.task(name="app.modules.partners.tasks.commission_hold_release")
def commission_hold_release() -> int:
    """Promote held ``pending`` commissions to ``payable``.

    Idempotent: a commission is only moved forward when its ``payable_at``
    has elapsed, and moving it a second time is a no-op.
    """
    import asyncio

    async def _run() -> int:
        session_maker = get_session_maker()
        async with session_maker() as session:
            try:
                count = await commission_service.release_payable(session)
                await session.commit()
                return count
            except Exception:
                await session.rollback()
                raise

    return asyncio.run(_run())
