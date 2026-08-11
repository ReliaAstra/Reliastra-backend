import logging
from celery import Celery
from app.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "reliastra",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.modules.checks.tasks",
        "app.modules.incidents.tasks",
        "app.modules.evidence.tasks",
        "app.modules.notifications.tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_always_eager=False,  # Can be set to True in tests
    beat_schedule={
        "schedule-checks-every-10-seconds": {
            "task": "app.modules.checks.tasks.schedule_checks",
            "schedule": 10.0,
        },
    },
)
