import logging
from typing import Any
from app.infrastructure.celery_app import celery_app
from app.modules.checks.tasks import run_async
from app.db.session import get_session_maker

logger = logging.getLogger(__name__)


@celery_app.task(name="app.modules.notifications.tasks.dispatch_notification")
def dispatch_notification(alert_dict: dict[str, Any]) -> int:
    async def _run() -> int:
        session_maker = get_session_maker()
        async with session_maker() as session:
            try:
                from app.modules.notifications.schemas import AlertPayload
                from app.modules.notifications.service import notification_service

                alert = AlertPayload.model_validate(alert_dict)
                sent = await notification_service.dispatch_alert(session, alert)
                return sent
            except Exception as exc:
                logger.exception("Error in dispatch_notification task: %s", exc)
                return 0

    return run_async(_run())
