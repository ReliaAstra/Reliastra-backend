import logging
from app.infrastructure.celery_app import celery_app
from app.modules.checks.tasks import run_async
from app.db.session import get_session_maker

logger = logging.getLogger(__name__)


@celery_app.task(name="app.modules.vendors.tasks.seed_vendors")
def seed_vendors_task() -> int:
    async def _run() -> int:
        session_maker = get_session_maker()
        async with session_maker() as session:
            try:
                from app.modules.vendors.service import vendor_service
                count = await vendor_service.seed_vendors(session)
                await session.commit()
                return count
            except Exception as exc:
                await session.rollback()
                logger.exception("Error seeding vendors: %s", exc)
                return 0

    return run_async(_run())
