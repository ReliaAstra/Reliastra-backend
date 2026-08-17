import logging
from celery import Celery
from celery.schedules import crontab
from celery.signals import task_postrun, task_prerun, task_failure
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
        "app.modules.api_keys.tasks",
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
        # Check scheduling no longer lives in Celery beat. The Redis ZSET
        # queue (app.infrastructure.scheduler) is the single scheduling path:
        # it polls `reliastra:check_queue` every 5s and fires
        # `execute_check` when entries become due.
        "observation-outbox-process": {
            "task": "app.modules.observations.tasks.process_outbox",
            "schedule": 10.0,
        },
        "retention-cleanup-monthly": {
            "task": "app.modules.observations.tasks.retention_cleanup",
            "schedule": crontab(minute=0, hour=3, day_of_month=1),
        },
        "aggregate-observation-daily": {
            "task": "app.modules.observations.tasks.daily_aggregation",
            "schedule": crontab(minute=0, hour=4),
        },
        "ensure-check-partitions-monthly": {
            "task": "app.modules.checks.tasks.ensure_check_result_partitions",
            "schedule": crontab(minute=0, hour=2, day_of_month=1),
        },
        "flush-api-key-last-used": {
            "task": "app.modules.api_keys.tasks.flush_api_key_last_used",
            "schedule": 300.0,
        },
    },
)


# ---------------------------------------------------------------------------
# Distributed tracing + Prometheus instrumentation for every Celery task.
# ---------------------------------------------------------------------------

@task_prerun.connect
def _on_task_prerun(task_id=None, task=None, args=None, kwargs=None, **extra):
    request_id = (kwargs or {}).get("request_id")
    logger.info(
        "Celery task starting: name=%s id=%s request_id=%s",
        task.name if task else "unknown",
        task_id,
        request_id or "-",
    )


@task_postrun.connect
def _on_task_postrun(task_id=None, task=None, state=None, **extra):
    try:
        from app.core.metrics import celery_tasks_total

        celery_tasks_total.labels(
            task=task.name if task else "unknown", status=state or "unknown"
        ).inc()
    except Exception:  # pragma: no cover - metrics must never break tasks
        pass


@task_failure.connect
def _on_task_failure(task_id=None, task=None, exception=None, **extra):
    try:
        from app.core.metrics import celery_tasks_total

        celery_tasks_total.labels(
            task=task.name if task else "unknown", status="failure"
        ).inc()
    except Exception:  # pragma: no cover - metrics must never break tasks
        pass
    logger.warning(
        "Celery task failed: name=%s id=%s error=%s",
        task.name if task else "unknown",
        task_id,
        exception,
    )
