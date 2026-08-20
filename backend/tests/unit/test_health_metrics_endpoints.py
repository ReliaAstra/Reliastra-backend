"""Tests for FIX 12 (Prometheus /metrics) and FIX 13 (/health/live + /health/ready)."""

import pytest


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_prometheus_text(async_client):
    res = await async_client.get("/metrics")
    assert res.status_code == 200
    assert "text/plain" in res.headers["content-type"]
    body = res.text
    assert "reliastra_checks_total" in body
    assert "reliastra_check_latency_seconds" in body
    assert "reliastra_incidents_total" in body


@pytest.mark.asyncio
async def test_health_live_is_cheap(async_client):
    res = await async_client.get("/health/live")
    assert res.status_code == 200
    payload = res.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "reliastra-backend"


@pytest.mark.asyncio
async def test_health_ready_reports_db_and_redis(async_client):
    res = await async_client.get("/health/ready")
    assert res.status_code == 200
    payload = res.json()
    assert payload["status"] == "ok"
    assert "database" in payload["checks"]
    assert "redis" in payload["checks"]


@pytest.mark.asyncio
async def test_health_legacy_endpoint_still_works(async_client):
    res = await async_client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
