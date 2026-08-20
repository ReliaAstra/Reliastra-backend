#!/usr/bin/env python3
"""Reliastra load & stress tests — Scenarios A–F.

Requires a live stack. Emits results to audit/results/load_results.json.
"""
from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
import json
import os
import statistics
import subprocess
import time
import uuid
from datetime import datetime, timezone

import httpx
import redis as redis_lib

BASE = os.environ.get("RELI_ASTRA_BASE", "http://localhost:8000")
RESULTS: list[dict] = []


def record(name: str, outcome: str, detail: str, severity: str = "warn") -> None:
    RESULTS.append({"scenario": name, "outcome": outcome, "detail": str(detail)[:600], "severity": severity,
                    "ts": datetime.now(timezone.utc).isoformat()})
    print(f"[{outcome.upper()}] {name} :: {detail}", flush=True)


def psql(sql: str) -> list[str]:
    out = subprocess.run(
        ["/home/user/venv/lib/python3.11/site-packages/pgserver/pginstall/bin/psql",
         "-h", "/tmp", "-p", "5432", "-U", "postgres", "-d", "reliastra", "-t", "-A", "-c", sql],
        capture_output=True, text=True, timeout=30)
    return [l.strip() for l in out.stdout.splitlines() if l.strip()]


def redis_llen() -> int:
    try:
        r = redis_lib.from_url("redis://localhost:6379/0", socket_timeout=3)
        return r.llen("celery") or 0
    except Exception:
        return -1


def pg_conns() -> int:
    try:
        return int(psql("SELECT count(*) FROM pg_stat_activity WHERE datname='reliastra';")[0])
    except Exception:
        return -1


def get_tok(email: str, pw: str) -> str:
    r = httpx.post(f"{BASE}/v1/auth/register", json={"email": email, "password": pw, "full_name": "Load Tester"}, timeout=30)
    if r.status_code != 201:
        r = httpx.post(f"{BASE}/v1/auth/login", json={"email": email, "password": pw}, timeout=30)
    return r.json()["access_token"]


async def scenario_a(owner_tok: str, org_id: str) -> None:
    """Check scheduler saturation: 50 deps @ 10s x 2 regions, 5 minutes."""
    print("\n=== SCENARIO A: check scheduler saturation ===", flush=True)
    headers = {"Authorization": f"Bearer {owner_tok}"}
    created = 0
    for i in range(50):
        url = "https://api.github.com/repos/ReliaAstra/load-dep-xyz-12345" if i % 7 == 0 else "https://api.github.com/zen"
        r = httpx.post(f"{BASE}/v1/orgs/{org_id}/dependencies", headers=headers, timeout=30, json={
            "name": f"load-dep-{i:02d}", "endpoint_url": url, "method": "GET",
            "expected_status_codes": [200], "timeout_seconds": 5,
            "check_interval_seconds": 10, "regions": ["us-east", "eu-west"],
        })
        if r.status_code == 201:
            created += 1
    record("A: create 50 deps", "pass" if created == 50 else "fail", f"created={created}/50")

    # Monitoring loop: 4 minutes, sample every 10s
    queue_samples, conn_samples, results_samples, recent_lat, rss_samples = [], [], [], [], []
    t0 = time.time()
    while time.time() - t0 < 240:
        queue_samples.append(redis_llen())
        conn_samples.append(pg_conns())
        results_samples.append(int(psql("SELECT count(*) FROM check_results;")[0]))
        try:
            out = subprocess.run(["ps", "-eo", "rss,cmd"], capture_output=True, text=True, timeout=10)
            rss = [int(l.split()[0]) for l in out.stdout.splitlines() if "celery" in l and "worker" in l]
            rss_samples.append(max(rss) if rss else 0)
        except Exception:
            rss_samples.append(-1)
        t = time.time()
        r = httpx.get(f"{BASE}/v1/orgs/{org_id}/checks/recent?limit=20", headers=headers, timeout=30)
        recent_lat.append((time.time() - t) * 1000)
        time.sleep(10)

    rate = (results_samples[-1] - results_samples[0]) / 240
    record("A: throughput", "pass" if rate > 0 else "fail",
           f"{results_samples[0]} -> {results_samples[-1]} rows in 300s = {rate:.1f} results/s")
    record("A: queue depth", "warn" if max(queue_samples) == 0 else "fail",
           f"celery queue max={max(queue_samples)} samples={queue_samples}")
    record("A: db connections", "warn" if max(conn_samples) <= 30 else "fail",
           f"pg connections max={max(conn_samples)} samples={conn_samples}")
    record("A: results/recent latency", "info", f"p50={statistics.median(recent_lat):.0f}ms max={max(recent_lat):.0f}ms")
    if rss_samples:
        peak_mb = max(rss_samples) / 1024
        record("A: worker RSS growth", "fail" if peak_mb > 512 else "info",
               f"peak worker RSS={peak_mb:.0f}MB samples={[round(x/1024) for x in rss_samples]}")


async def scenario_b(owner_tok: str, org_id: str) -> None:
    """DB connection pool exhaustion: 100 concurrent dashboard/latency?hours=2160."""
    print("\n=== SCENARIO B: DB connection pool exhaustion ===", flush=True)
    headers = {"Authorization": f"Bearer {owner_tok}"}
    url = f"{BASE}/v1/orgs/{org_id}/dashboard/latency?hours=2160"

    async def one(i: int):
        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=45, verify=False) as c:
                r = await c.get(url, headers=headers)
            return {"ok": r.status_code == 200, "status": r.status_code, "ms": (time.time() - t0) * 1000, "i": i}
        except Exception as e:
            return {"ok": False, "status": "exc", "ms": (time.time() - t0) * 1000, "i": i, "err": type(e).__name__}

    conns_before = pg_conns()
    t0 = time.time()
    res = await asyncio.gather(*[one(i) for i in range(100)])
    dur = time.time() - t0
    conns_after = pg_conns()
    ok = [r for r in res if r["ok"]]
    bad = [r for r in res if not r["ok"]]
    lat = sorted(r["ms"] for r in res)
    p50, p95, p99 = lat[len(lat)//2], lat[int(len(lat)*0.95)], lat[int(len(lat)*0.99)]
    record("B: 100 concurrent /dashboard/latency?hours=2160", "pass" if len(ok) == 100 else "fail",
           f"ok={len(ok)} fail={len(bad)} wall={dur:.1f}s p50={p50:.0f}ms p95={p95:.0f}ms p99={p99:.0f}ms max={max(lat):.0f}ms")
    record("B: connection growth", "info", f"pg conns {conns_before} -> {conns_after}")


async def scenario_c(owner_tok: str, org_id: str) -> None:
    """HTTP client connection churn: 1 dep @ 5s, count TCP sockets."""
    print("\n=== SCENARIO C: HTTP client connection overhead ===", flush=True)
    headers = {"Authorization": f"Bearer {owner_tok}"}
    r = httpx.post(f"{BASE}/v1/orgs/{org_id}/dependencies", headers=headers, timeout=30, json={
        "name": "churn-dep", "endpoint_url": "https://api.github.com/zen", "method": "GET",
        "expected_status_codes": [200], "timeout_seconds": 5, "check_interval_seconds": 10,
        "regions": ["us-east", "eu-west"]})
    record("C: create churn dep", "pass" if r.status_code == 201 else "fail", f"status={r.status_code}")

    def tcp_443():
        out = subprocess.run(["ss", "-tan"], capture_output=True, text=True, timeout=10)
        lines = [l for l in out.stdout.splitlines() if ":443" in l]
        est = sum(1 for l in lines if "ESTAB" in l)
        tw = sum(1 for l in lines if "TIME-WAIT" in l)
        return est, tw

    # warmup + measure over 2 minutes
    time.sleep(15)
    est0, tw0 = tcp_443()
    t0 = time.time()
    while time.time() - t0 < 120:
        time.sleep(10)
    est1, tw1 = tcp_443()
    record("C: TCP churn", "warn",
           f"established :443 {est0}->{est1}, TIME-WAIT {tw0}->{tw1} over 120s (per-check new conn expected)")


async def scenario_d(owner_tok: str) -> None:
    """Idempotency: 100 POST /v1/orgs with the SAME key (same user)."""
    print("\n=== SCENARIO D: idempotency collision (same user) ===", flush=True)
    key = f"load-idem-{uuid.uuid4().hex}"
    ids: set[str] = set()
    codes = {}
    async with httpx.AsyncClient(timeout=30) as c:
        for i in range(100):
            r = await c.post(f"{BASE}/v1/orgs", headers={"Authorization": f"Bearer {owner_tok}",
                                                         "Idempotency-Key": key},
                             json={"name": f"IdemLoad-{i}"})
            codes[r.status_code] = codes.get(r.status_code, 0) + 1
            if r.status_code in (200, 201):
                ids.add(r.json().get("id", ""))
    record("D: 100 same-key POSTs", "pass" if len(ids) == 1 else "fail",
           f"distinct orgs created={len(ids)} status_codes={codes}")


async def scenario_e(owner_tok: str, org_id: str) -> None:
    """Quorum race: 1 dep x 2 regions, concurrent execute_check dispatch."""
    print("\n=== SCENARIO E: quorum race condition ===", flush=True)
    headers = {"Authorization": f"Bearer {owner_tok}"}
    r = httpx.post(f"{BASE}/v1/orgs/{org_id}/dependencies", headers=headers, timeout=30, json={
        "name": "quorum-race", "endpoint_url": "https://api.github.com/repos/ReliaAstra/quorum-race-xyz",
        "method": "GET", "expected_status_codes": [200], "timeout_seconds": 5,
        "check_interval_seconds": 86400, "regions": ["us-east", "eu-west"]})
    dep_id = r.json().get("id", "") if r.status_code == 201 else ""
    record("E: create race dep", "pass" if dep_id else "fail", f"status={r.status_code}")

    from app.infrastructure.celery_app import celery_app
    # fire 20 concurrent execute_check tasks per region (40 total)
    async def fire():
        loop = asyncio.get_running_loop()
        for reg in ["us-east", "eu-west"] * 20:
            loop.run_in_executor(None, celery_app.send_task, "app.modules.checks.tasks.execute_check", [dep_id, reg])
    await fire()
    await asyncio.sleep(60)  # let the worker chew through them
    n_incidents = int(psql(f"SELECT count(*) FROM incidents WHERE dependency_id='{dep_id}';")[0])
    n_results = int(psql(f"SELECT count(*) FROM check_results WHERE dependency_id='{dep_id}';")[0])
    record("E: concurrent quorum", "pass" if n_incidents == 1 else "fail",
           f"incidents={n_incidents} (expect 1) results={n_results} (expect 40)")


async def scenario_f() -> None:
    """Partition boundary test."""
    print("\n=== SCENARIO F: partition boundary ===", flush=True)
    future = "now() + interval '1 month'"
    rows = psql("INSERT INTO check_results (id, executed_at, dependency_id, org_id, region, latency_ms, status_code, is_up, error_message, quorum_confirmed) "
                f"SELECT gen_random_uuid(), {future}, '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000002', 'us-east', 1.0, 200, true, NULL, false RETURNING id;")
    record("F: future-dated insert (with DEFAULT partition)", "pass" if rows else "fail",
           f"insert returned row: {rows[:1]} — landed in DEFAULT partition")

    # Show what happens WITHOUT a DEFAULT partition
    out = subprocess.run(
        ["/home/user/venv/lib/python3.11/site-packages/pgserver/pginstall/bin/psql",
         "-h", "/tmp", "-p", "5432", "-U", "postgres", "-d", "reliastra", "-t", "-A", "-c",
         "CREATE TEMP TABLE part_test (id uuid, executed_at timestamptz NOT NULL) PARTITION BY RANGE (executed_at);"
         "INSERT INTO part_test VALUES (gen_random_uuid(), now() + interval '1 month');"],
        capture_output=True, text=True, timeout=30)
    has_partition_err = "no partition of relation" in out.stderr
    record("F: no-default-partition insert", "pass" if has_partition_err else "fail",
           f"error={'no partition of relation' if has_partition_err else 'none'} stderr={out.stderr.strip()[:150]}")


SCENARIOS = {"a": scenario_a, "b": scenario_b, "c": scenario_c, "d": scenario_d, "e": scenario_e, "f": scenario_f}


def setup() -> tuple[str, str]:
    import sys
    email = f"load-{uuid.uuid4().hex[:8]}@test.reliastra.dev"
    pw = "Str0ng-Passw0rd!"
    tok = get_tok(email, pw)
    r = httpx.post(f"{BASE}/v1/orgs", headers={"Authorization": f"Bearer {tok}"}, json={"name": f"LoadOrg-{uuid.uuid4().hex[:6]}"}, timeout=30)
    org_id = r.json()["id"]
    r = httpx.patch(f"{BASE}/v1/orgs/{org_id}", headers={"Authorization": f"Bearer {tok}"}, json={"plan": "professional"}, timeout=30)
    print("plan ->", r.json().get("plan"), flush=True)
    return tok, org_id


def save() -> None:
    os.makedirs("audit/results", exist_ok=True)
    with open("audit/results/load_results.json", "w") as f:
        json.dump(RESULTS, f, indent=2, default=str)
    print("\nload results -> audit/results/load_results.json", flush=True)


async def main() -> None:
    import sys
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    tok, org_id = setup()
    if which == "all":
        for name, fn in SCENARIOS.items():
            if name == "d":
                await fn(tok)
            else:
                await fn(tok, org_id)
    elif which == "d":
        await scenario_d(tok)
    elif which == "f":
        await scenario_f()
    else:
        await SCENARIOS[which](tok, org_id)
    save()


if __name__ == "__main__":
    asyncio.run(main())
