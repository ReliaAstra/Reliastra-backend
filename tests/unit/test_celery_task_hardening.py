"""Celery timeouts, retries, and env-driven beat schedule."""

from app.config import settings
from app.infrastructure.celery_app import celery_app
from app.modules.checks.tasks import execute_check, schedule_checks
from app.modules.evidence.tasks import generate_evidence_report


def test_celery_app_has_global_time_limits():
    assert celery_app.conf.task_time_limit == settings.CELERY_TASK_TIME_LIMIT
    assert celery_app.conf.task_soft_time_limit == settings.CELERY_TASK_SOFT_TIME_LIMIT
    assert celery_app.conf.task_acks_late is True


def test_beat_schedule_uses_configured_interval():
    entry = celery_app.conf.beat_schedule["schedule-checks-periodic"]
    assert entry["schedule"] == float(settings.CHECK_SCHEDULE_SECONDS)


def test_execute_check_retries_and_time_limits():
    assert execute_check.max_retries == 3
    assert execute_check.soft_time_limit == 60
    assert execute_check.time_limit == 90
    assert Exception in (execute_check.autoretry_for or ())


def test_schedule_checks_retries():
    assert schedule_checks.max_retries == 2
    assert Exception in (schedule_checks.autoretry_for or ())


def test_evidence_task_retries():
    assert generate_evidence_report.max_retries == 3
    assert Exception in (generate_evidence_report.autoretry_for or ())
