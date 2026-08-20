"""Prometheus metrics for Reliastra self-observability.

Exposed at ``GET /metrics`` (see ``app/main.py``). All instruments are
process-local counters/histograms; Prometheus scrapes every instance.

Metrics:
* ``reliastra_checks_total{region,status}``      — probe outcomes
* ``reliastra_check_latency_seconds{region}``    — probe latency
* ``reliastra_incidents_total{action}``          — incidents opened/resolved
* ``reliastra_celery_tasks_total{task,status}``  — Celery task completions
* ``reliastra_http_requests_total{method,status}``— inbound HTTP requests
* ``reliastra_ai_generation_total{provider_type,status}`` — AI explanation attempts
* ``reliastra_ai_generation_latency_seconds{provider_type}`` — AI latency
"""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)

checks_total = Counter(
    "reliastra_checks_total",
    "Total dependency checks executed",
    ["region", "status"],
)

check_latency = Histogram(
    "reliastra_check_latency_seconds",
    "Dependency check latency in seconds",
    ["region"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

incidents_total = Counter(
    "reliastra_incidents_total",
    "Total incidents opened and resolved",
    ["action"],
)

celery_tasks_total = Counter(
    "reliastra_celery_tasks_total",
    "Total Celery task completions",
    ["task", "status"],
)

http_requests_total = Counter(
    "reliastra_http_requests_total",
    "Total inbound HTTP requests",
    ["method", "status"],
)

ai_generation_total = Counter(
    "reliastra_ai_generation_total",
    "Total AI explanation generation attempts",
    ["provider_type", "status"],
)

ai_generation_latency = Histogram(
    "reliastra_ai_generation_latency_seconds",
    "AI explanation generation latency in seconds",
    ["provider_type"],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)


def render_metrics() -> bytes:
    """Render the current Prometheus exposition text."""
    return generate_latest()


def metrics_content_type() -> str:
    """Return the correct Content-Type for the /metrics endpoint."""
    return CONTENT_TYPE_LATEST
