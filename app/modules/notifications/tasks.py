import logging
from typing import Any
from app.infrastructure.async_tasks import async_task_body
from app.infrastructure.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.modules.notifications.tasks.dispatch_notification",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def dispatch_notification(
    alert_dict: dict[str, Any], request_id: str | None = None
) -> int:
    async def _run(session) -> int:
        try:
            from app.modules.notifications.schemas import AlertPayload
            from app.modules.notifications.service import notification_service

            alert = AlertPayload.model_validate(alert_dict)
            return await notification_service.dispatch_alert(session, alert)
        except Exception as exc:
            logger.exception(
                "Error in dispatch_notification task (request_id=%s): %s",
                request_id,
                exc,
            )
            return 0

    return async_task_body(_run)
