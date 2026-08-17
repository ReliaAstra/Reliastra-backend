import logging
from celery import Celery
from celery.schedules import crontab
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
