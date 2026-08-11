"""Celery worker and beat configuration."""

from __future__ import annotations

from celery import Celery

from app.config import Settings


def create_celery(settings: Settings) -> Celery:
    application = Celery(
        "reliastra",
        broker=settings.redis_url,
        backend=settings.redis_url,
        include=[
            "app.modules.checks.tasks",
            "app.modules.incidents.tasks",
            "app.modules.evidence.tasks",
            "app.modules.notifications.tasks",
        ],
    )
    application.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        task_routes={
            "checks.*": {"queue": "checks"},
            "evidence.*": {"queue": "evidence"},
            "notifications.*": {"queue": "notifications"},
            "incidents.*": {"queue": "checks"},
        },
        beat_schedule={
            "schedule-due-checks": {
                "task": "checks.schedule_checks",
                "schedule": 10.0,
            }
        },
    )
    return application


celery_app = create_celery(Settings())
