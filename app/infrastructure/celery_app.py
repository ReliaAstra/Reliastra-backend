import logging
from celery import Celery
from celery.schedules import crontab
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
        "app.modules.observations.tasks",
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
        "schedule-checks-periodic": {
            "task": "app.modules.checks.tasks.schedule_checks",
            "schedule": 30.0,
        },
        "retention-cleanup-monthly": {
            "task": "app.modules.observations.tasks.retention_cleanup",
            "schedule": crontab(minute=0, hour=3, day_of_month=1),
        },
        "aggregate-observation-daily": {
            "task": "app.modules.observations.tasks.daily_aggregation",
            "schedule": crontab(minute=0, hour=4),
        },
    },
)
