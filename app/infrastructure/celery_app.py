import logging
from celery import Celery
from celery.schedules import crontab
from celery.signals import task_postrun, task_prerun, task_failure
from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Import EVERY model module so the SQLAlchemy metadata (and FK graph) is
# complete inside the worker process.  Without this, any ORM flush that
# touches a cross-module FK fails with
# ``NoReferencedTableError: could not find table 'applications'`` — the
# worker's ``schedule_checks`` task would fail for every due dependency.
# The API process happens to work only because uvicorn's app import pulls in
# all routers (and therefore all models) transitively.
# ---------------------------------------------------------------------------
from app.modules import (  # noqa: F401
    admin,
    agencies,
    ai_integration,
    api_keys,
    attribution,
    auth,
    badges,
    billing,
    checks,
    dashboard,
    dependencies,
    evidence,
    evidence_gate,
    incidents,
    notifications,
    observations,
    organizations,
    partners,
    referrals,
    status_pages,
    timeline_share,
    users,
    vendor_submissions,
    vendors,
    webhooks,
)
from app.modules.admin import models as _admin_models  # noqa: F401
from app.modules.agencies import models as _agency_models  # noqa: F401
from app.modules.ai_integration import models as _ai_models  # noqa: F401
from app.modules.api_keys import models as _apikey_models  # noqa: F401
from app.modules.attribution import models as _attribution_models  # noqa: F401
from app.modules.auth import models as _auth_models  # noqa: F401
from app.modules.badges import models as _badge_models  # noqa: F401
from app.modules.billing import models as _billing_models  # noqa: F401
from app.modules.checks import models as _check_models  # noqa: F401
from app.modules.dependencies import models as _dep_models  # noqa: F401
from app.modules.evidence import models as _evidence_models  # noqa: F401
from app.modules.evidence_gate import models as _gate_models  # noqa: F401
from app.modules.incidents import models as _incident_models  # noqa: F401
from app.modules.notifications import models as _notif_models  # noqa: F401
from app.modules.observations import models as _obs_models  # noqa: F401
from app.modules.organizations import models as _org_models  # noqa: F401
from app.modules.partners import models as _partner_models  # noqa: F401
from app.modules.referrals import models as _referral_models  # noqa: F401
from app.modules.status_pages import models as _status_models  # noqa: F401
from app.modules.timeline_share import models as _timeline_models  # noqa: F401
from app.modules.users import models as _user_models  # noqa: F401
from app.modules.vendor_submissions import models as _submission_models  # noqa: F401
from app.modules.vendors import models as _vendor_models  # noqa: F401
from app.modules.webhooks import models as _webhook_models  # noqa: F401

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
        "app.modules.partners.tasks",
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
        # ── Partner network ──────────────────────────────────────────
        # Safety net for commissions the payment webhook failed to record.
        "partner-commission-calculation": {
            "task": "app.modules.partners.tasks.commission_calculation",
            "schedule": crontab(minute=20, hour="*/6"),
        },
        # Promote pending -> payable once the 30-day hold has elapsed.
        "partner-commission-hold-release": {
            "task": "app.modules.partners.tasks.commission_hold_release",
            "schedule": crontab(minute=15, hour=1),
        },
        # Close the previous month. Runs on the 1st, after hold release.
        "partner-commission-monthly-settlement": {
            "task": "app.modules.partners.tasks.commission_monthly_settlement",
            "schedule": crontab(minute=45, hour=1, day_of_month=1),
        },
        # Expire Year-1 earning windows so accrual stops on time.
        "partner-commission-reversal": {
            "task": "app.modules.partners.tasks.commission_reversal",
            "schedule": crontab(minute=30, hour=2),
        },
        "partner-tier-evaluation": {
            "task": "app.modules.partners.tasks.partner_tier_evaluation",
            "schedule": crontab(minute=0, hour=5),
        },
        "partner-fraud-analysis": {
            "task": "app.modules.partners.tasks.fraud_analysis",
            "schedule": crontab(minute=30, hour=5),
        },
        # Roll yesterday's clicks/conversions into per-country daily rows.
        "partner-geo-aggregation": {
            "task": "app.modules.partners.tasks.geo_aggregation",
            "schedule": crontab(minute=20, hour=4),
        },
        # Expire unconverted attribution touches past the window.
        "partner-referral-attribution-expiry": {
            "task": "app.modules.partners.tasks.referral_attribution_expiry",
            "schedule": crontab(minute=10, hour=3),
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
