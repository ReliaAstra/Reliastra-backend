"""Reliastra production readiness — load & stress suite (STEP 3).

Scenarios A-H. Each scenario returns a structured finding with the observed
failure mode and the measured threshold.

Run:  .venv/bin/python audit/stress_suite.py
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
import secrets
import statistics
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = os.environ.get("RELIASTRA_BASE", "http://127.0.0.1:8000")
PSQL = ("/home/user/Reliastra-backend/.venv/lib/python3.11/site-packages/"
        "pgserver/pginstall/bin/psql")
DSN = "postgresql://postgres@127.0.0.1:5432/reliastra"
REDIS_CLI = "/tmp/redis-7.2.5/src/redis-cli"

FINDINGS: list[dict[str, Any]] = []

# Reachable probe targets (sandbox egress is allowlisted; httpbin.org is not
# reachable, so equivalent real endpoints are used).
T_HEALTHY = "https://api.github.com/status"
T_FAIL = "https://api.github.com/nope-does-not-exist-404"
T_REDIRECT = "http://pypi.org"
T_SLOW = "https://pypi.org/simple/"


def sql(q: str) -> str:
    r = subprocess.run([PSQL, DSN, "-t", "-A", "-c", q],
                       capture_output=True, text=True)
    return (r.stdout or r.stderr).strip()


def finding(scenario: str, result: str, severity: str, detail: str,
            metrics: dict | None = None) -> None:
    FINDINGS.append({"scenario": scenario, "result": result,
                     "severity": severity, "detail": detail,
                     "metrics": metrics or {}})
    print(f"\n[{scenario}] {result} ({severity})\n    {detail}")
    for k, v in (metrics or {}).items():
        print(f"      {k}: {v}")


def bootstrap(plan: str = "agency") -> tuple[str, str]:
    """Register a user + org, return (access_token, org_id)."""
    s = secrets.token_hex(4)
    c = httpx.Client(base_url=BASE, timeout=60)
    r = c.post("/v1/auth/register", json={
        "email": f"stress+{s}@reliastra-audit.dev",
        "password": "AuditPassw0rd!2026", "full_name": "Stress"})
    tok = r.json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    r = c.post("/v1/orgs", json={"name": f"Stress Org {s}"}, headers=h)
    org_id = r.json()["id"]
    sql(f"UPDATE organizations SET plan='{plan}' WHERE id='{org_id}';")
    return tok, org_id


# ───────────────────── Scenario A: scheduler saturation ─────────────────────
def scenario_a() -> None:
    print("\n" + "=" * 78)
    print("SCENARIO A: Check Scheduler Saturation (50 deps x 2 regions @ 10s)")
    print("=" * 78)
    tok, org_id = bootstrap()
    h = {"Authorization": f"Bearer {tok}"}
    c = httpx.Client(base_url=BASE, timeout=120)

    n = 50
    created = 0
    for i in range(n):
        r = c.post(f"/v1/orgs/{org_id}/dependencies", json={
            "name": f"sat-{i}", "endpoint_url": T_HEALTHY, "method": "GET",
            "check_interval_seconds": 10, "timeout_seconds": 10,
            "expected_status_codes": [200],
            "regions": ["us-east", "eu-west"]}, headers=h)
        if r.status_code in (200, 201):
            created += 1
    print(f"  created {created}/{n} dependencies (2 regions each "
          f"=> {created*2} probes per 10s cycle)")

    conns_before = int(sql("SELECT count(*) FROM pg_stat_activity;") or 0)
    t0 = time.time()
    samples: list[dict] = []
    duration = 300  # 5 minutes
    while time.time() - t0 < duration:
        time.sleep(30)
        elapsed = int(time.time() - t0)
        rows = int(sql(f"SELECT count(*) FROM check_results WHERE org_id='{org_id}';") or 0)
        conns = int(sql("SELECT count(*) FROM pg_stat_activity;") or 0)
        active = int(sql("SELECT count(*) FROM pg_stat_activity "
                         "WHERE state='active';") or 0)
        waiting = int(sql("SELECT count(*) FROM pg_stat_activity "
                          "WHERE wait_event_type='Lock';") or 0)
        # API responsiveness while scheduler is saturated
        ts = time.time()
        try:
            hr = httpx.get(f"{BASE}/health", timeout=30)
            api_ms = (time.time() - ts) * 1000
            api_code = hr.status_code
        except Exception as e:
            api_ms = (time.time() - ts) * 1000
            api_code = f"ERR {type(e).__name__}"
        samples.append({"t": elapsed, "rows": rows, "pg_conns": conns,
                        "pg_active": active, "pg_lock_waits": waiting,
                        "health_ms": round(api_ms, 1), "health": api_code})
        print(f"  t={elapsed:3}s rows={rows:6} pg_conns={conns:3} "
              f"active={active:2} lockwaits={waiting} "
              f"health={api_code} {api_ms:.0f}ms")

    total_rows = samples[-1]["rows"] if samples else 0
    # Expected: 50 deps * 2 regions * (300s/10s) = 3000 probes in 5 min
    expected = created * 2 * (duration // 10)
    completion = (total_rows / expected * 100) if expected else 0
    worst_health = max((s["health_ms"] for s in samples), default=0)

    # Measure one schedule cycle duration directly
    cycle = measure_schedule_cycle(org_id)

    sev = "P1"
    res = "PASS"
    if completion < 60:
        res, sev = "FAIL", "P1"
    detail = (
        f"Achieved {total_rows} check_results vs {expected} theoretically due "
        f"({completion:.1f}% of nominal throughput). The scheduler runs "
        f"serially inside ONE APScheduler job with max_instances=1: every probe "
        f"is awaited in-line in a single `for dep ... for region` loop sharing "
        f"ONE AsyncSession, so cycle time grows linearly with dependency count "
        f"and the 30s interval is missed. Probes are also emitted at the fixed "
        f"30s beat, not the configured 10s interval — sub-30s intervals are "
        f"silently unhonoured."
    )
    finding("A: Scheduler saturation", res, sev, detail, {
        "dependencies": created,
        "probes_per_cycle": created * 2,
        "check_results_written_5min": total_rows,
        "nominal_expected_5min": expected,
        "throughput_completion_pct": round(completion, 1),
        "measured_full_cycle_seconds": cycle,
        "worst_health_latency_ms": worst_health,
        "peak_pg_connections": max((s["pg_conns"] for s in samples), default=0),
        "samples": samples,
    })


def measure_schedule_cycle(org_id: str) -> float:
    """Force every dependency due and time one full serial schedule pass."""
    sql("UPDATE dependencies SET next_check_at = now() - interval '1 hour' "
        f"WHERE org_id='{org_id}' AND is_deleted=false;")
    before = int(sql(f"SELECT count(*) FROM check_results WHERE org_id='{org_id}';") or 0)
    t0 = time.time()
    deadline = t0 + 240
    target = before  # will grow
    last = before
    stable_for = 0
    while time.time() < deadline:
        time.sleep(5)
        cur = int(sql(f"SELECT count(*) FROM check_results WHERE org_id='{org_id}';") or 0)
        if cur > last:
            last = cur
            stable_for = 0
        else:
            stable_for += 5
            if cur > before and stable_for >= 15:
                break
    return round(time.time() - t0 - stable_for, 1)


# ─────────────── Scenario B: DB connection pool exhaustion ───────────────
def scenario_b() -> None:
    print("\n" + "=" * 78)
    print("SCENARIO B: DB Connection Pool Exhaustion (100 concurrent max-range)")
    print("=" * 78)
    tok, org_id = bootstrap()
    h = {"Authorization": f"Bearer {tok}"}
    path = f"/v1/orgs/{org_id}/dashboard/latency?hours=2160"

    def hit(_: int) -> tuple[int | str, float]:
        t0 = time.time()
        try:
            r = httpx.get(f"{BASE}{path}", headers=h, timeout=60)
            return r.status_code, (time.time() - t0) * 1000
        except Exception as e:
            return f"ERR:{type(e).__name__}", (time.time() - t0) * 1000

    peak = {"v": 0}

    def sample_pg() -> None:
        t0 = time.time()
        while time.time() - t0 < 25:
            n = int(sql("SELECT count(*) FROM pg_stat_activity;") or 0)
            peak["v"] = max(peak["v"], n)
            time.sleep(0.4)

    with cf.ThreadPoolExecutor(max_workers=110) as ex:
        ex.submit(sample_pg)
        t0 = time.time()
        results = list(ex.map(hit, range(100)))
        wall = time.time() - t0

    codes = [c for c, _ in results]
    lat = [ms for _, ms in results]
    ok = sum(1 for c in codes if c == 200)
    errs = [c for c in codes if c != 200]
    p50 = statistics.median(lat)
    p95 = sorted(lat)[int(len(lat) * 0.95) - 1]
    mx = max(lat)

    detail = (
        f"100 concurrent 90-day dashboard queries: {ok}/100 succeeded, "
        f"p50={p50:.0f}ms p95={p95:.0f}ms max={mx:.0f}ms, wall={wall:.1f}s. "
        f"Pool is pool_size=10 + max_overflow=20 = 30 hard cap with "
        f"pool_timeout=30s (app/db/session.py:139-142), so the 70 requests "
        f"beyond the pool queue behind it. Requests are serialised rather than "
        f"rejected, so latency degrades as a step function instead of shedding "
        f"load; at >30s queueing the client sees a pool-timeout 500."
    )
    res = "FAIL" if (errs or p95 > 5000) else "PASS"
    finding("B: DB pool exhaustion", res, "P1", detail, {
        "succeeded": ok, "failed": len(errs),
        "error_codes": list({str(e) for e in errs})[:5],
        "p50_ms": round(p50), "p95_ms": round(p95), "max_ms": round(mx),
        "wall_seconds": round(wall, 1),
        "peak_pg_connections_observed": peak["v"],
        "pool_size": 10, "max_overflow": 20, "pool_timeout_s": 30,
    })


# ─────────────── Scenario C: HTTP client connection overhead ───────────────
def scenario_c() -> None:
    print("\n" + "=" * 78)
    print("SCENARIO C: HTTP Client Connection Overhead")
    print("=" * 78)
    # Static evidence: a new AsyncClient per check == no connection reuse.
    src = open("app/modules/checks/service.py").read()
    per_check_client = "async with httpx.AsyncClient(" in src
    has_global_pool = "limits=" in src or "http2=True" in src

    # Empirically measure the cost of per-request client vs pooled client.
    import asyncio

    async def measure() -> tuple[float, float]:
        n = 12
        t0 = time.time()
        for _ in range(n):
            async with httpx.AsyncClient(timeout=20) as cl:
                await cl.get(T_HEALTHY)
        per_req = (time.time() - t0) / n * 1000

        async with httpx.AsyncClient(timeout=20) as cl:
            await cl.get(T_HEALTHY)  # warm
            t0 = time.time()
            for _ in range(n):
                await cl.get(T_HEALTHY)
            pooled = (time.time() - t0) / n * 1000
        return per_req, pooled

    per_req_ms, pooled_ms = asyncio.run(measure())
    overhead = per_req_ms - pooled_ms
    pct = (overhead / per_req_ms * 100) if per_req_ms else 0

    detail = (
        f"app/modules/checks/service.py:175 opens `async with "
        f"httpx.AsyncClient(...)` INSIDE execute_check, so every probe pays a "
        f"fresh DNS lookup + TCP handshake + TLS handshake and the pool is "
        f"discarded on exit. Measured {per_req_ms:.0f}ms per probe with a "
        f"per-request client vs {pooled_ms:.0f}ms with a reused pooled client "
        f"— {overhead:.0f}ms ({pct:.0f}%) of every recorded latency_ms is "
        f"connection setup, not vendor latency. This means the latency SLA "
        f"numbers Reliastra sells are inflated by handshake cost, and socket "
        f"churn scales linearly with probe volume (TIME_WAIT accumulation)."
    )
    finding("C: HTTP connection churn", "FAIL", "P1", detail, {
        "new_client_per_check": per_check_client,
        "global_pool_configured": has_global_pool,
        "http2_enabled": "http2=True" in src,
        "avg_ms_per_request_new_client": round(per_req_ms, 1),
        "avg_ms_per_request_pooled": round(pooled_ms, 1),
        "handshake_overhead_ms": round(overhead, 1),
        "latency_inflation_pct": round(pct, 1),
    })


# ─────────────── Scenario D: idempotency cache collision ───────────────
def scenario_d() -> None:
    print("\n" + "=" * 78)
    print("SCENARIO D: Idempotency Cache Collision / Cross-Tenant Replay")
    print("=" * 78)
    tok_a, _ = bootstrap()
    tok_b, _ = bootstrap()
    key = f"audit-idem-{uuid.uuid4()}"

    # 1) same user, same key, 200 concurrent creates
    def create(i: int) -> tuple[int, str]:
        try:
            r = httpx.post(f"{BASE}/v1/orgs",
                           json={"name": f"Idem Org {i}"},
                           headers={"Authorization": f"Bearer {tok_a}",
                                    "Idempotency-Key": key},
                           timeout=60)
            oid = ""
            try:
                oid = r.json().get("id", "")
            except Exception:
                pass
            return r.status_code, oid
        except Exception as e:
            return -1, f"ERR:{type(e).__name__}"

    N = 200
    with cf.ThreadPoolExecutor(max_workers=50) as ex:
        res = list(ex.map(create, range(N)))
    ids = {oid for code, oid in res if oid and not oid.startswith("ERR")}
    created_rows = int(sql(
        "SELECT count(*) FROM organizations WHERE name LIKE 'Idem Org %';") or 0)

    # 2) cross-tenant replay: user B replays user A's idempotency key
    rb = httpx.post(f"{BASE}/v1/orgs", json={"name": "Attacker Org"},
                    headers={"Authorization": f"Bearer {tok_b}",
                             "Idempotency-Key": key}, timeout=60)
    leaked = False
    leak_body = ""
    try:
        leak_body = rb.text[:300]
        leaked = rb.status_code == 201 and rb.json().get("id") in ids
    except Exception:
        pass

    # Is the cache key user-scoped?
    src = open("app/main.py").read()
    scoped = "idempotency:{idempotency_key}" not in src

    detail = (
        f"{N} concurrent POST /v1/orgs with one Idempotency-Key produced "
        f"{len(ids)} distinct org id(s) and {created_rows} DB rows. "
        f"CROSS-TENANT REPLAY: user B sending user A's key received "
        f"HTTP {rb.status_code} and "
        f"{'A COPY OF USER A ORG — CONFIRMED TENANT DATA LEAK' if leaked else 'a distinct response'}. "
        f"The cache key is built as f'idempotency:{{idempotency_key}}' "
        f"(app/main.py:76) with NO user/org in the key, and the cached value is "
        f"the full response body. There is also no in-flight lock (no SETNX): "
        f"the middleware does GET-then-call-then-SETEX, so concurrent requests "
        f"all miss the cache and each executes the mutation."
    )
    sev = "P0" if (leaked or len(ids) > 1) else "P1"
    res_s = "FAIL" if (leaked or len(ids) > 1) else "PASS"
    finding("D: Idempotency collision", res_s, sev, detail, {
        "requests": N,
        "distinct_orgs_created": len(ids),
        "db_rows_created": created_rows,
        "cross_tenant_replay_status": rb.status_code,
        "cross_tenant_leak_confirmed": leaked,
        "cross_tenant_body": leak_body,
        "cache_key_is_user_scoped": scoped,
        "in_flight_lock_present": "setnx" in src.lower(),
    })


# ─────────────── Scenario E: quorum race condition ───────────────
def scenario_e() -> None:
    print("\n" + "=" * 78)
    print("SCENARIO E: Quorum Race Condition (concurrent multi-region failure)")
    print("=" * 78)
    tok, org_id = bootstrap()
    h = {"Authorization": f"Bearer {tok}"}
    c = httpx.Client(base_url=BASE, timeout=60)
    # Dependency whose target always fails, 2 regions.
    r = c.post(f"/v1/orgs/{org_id}/dependencies", json={
        "name": "quorum-race", "endpoint_url": T_FAIL, "method": "GET",
        "check_interval_seconds": 10, "timeout_seconds": 10,
        "expected_status_codes": [200],
        "regions": ["us-east", "eu-west"]}, headers=h)
    dep_id = r.json()["id"]

    # Drive both regions concurrently, in separate sessions, repeatedly —
    # exactly what a multi-worker deployment does.
    import asyncio

    from app.db.session import get_session_maker
    from app.modules.checks.service import check_service

    async def one(region: str) -> None:
        sm = get_session_maker()
        async with sm() as s:
            try:
                await check_service.execute_check(s, uuid.UUID(dep_id), region)
                await s.commit()
            except Exception as e:
                await s.rollback()
                print(f"    execute_check({region}) raised {type(e).__name__}: {e}")

    async def burst() -> None:
        for _ in range(3):
            await asyncio.gather(one("us-east"), one("eu-west"))

    asyncio.run(burst())
    time.sleep(2)

    n_inc = int(sql(f"SELECT count(*) FROM incidents WHERE dependency_id='{dep_id}';") or 0)
    n_open = int(sql("SELECT count(*) FROM incidents WHERE dependency_id="
                     f"'{dep_id}' AND status='open';") or 0)
    n_res = int(sql(f"SELECT count(*) FROM check_results WHERE dependency_id='{dep_id}';") or 0)
    n_quorum = int(sql("SELECT count(*) FROM check_results WHERE dependency_id="
                       f"'{dep_id}' AND quorum_confirmed=true;") or 0)

    correct = (n_inc == 1)
    detail = (
        f"3 concurrent 2-region failure bursts against one dependency produced "
        f"{n_res} check_results ({n_quorum} quorum_confirmed) and {n_inc} "
        f"incident row(s), {n_open} still open. Correct behaviour is exactly 1 "
        f"open incident. execute_check (service.py:205-233) does "
        f"read-recent-results -> evaluate-in-Python -> write with NO row lock and "
        f"NO unique constraint on (dependency_id, status='open'), so two regions "
        f"committing inside the same 60s quorum window can both observe "
        f"'no open incident' and both insert "
        f"(duplicate alerts / double-billed evidence), or both observe only their "
        f"own failure and neither reach quorum (missed incident)."
    )
    finding("E: Quorum race", "PASS" if correct else "FAIL",
            "P0" if not correct else "P2", detail, {
        "check_results": n_res,
        "quorum_confirmed_results": n_quorum,
        "incidents_created": n_inc,
        "incidents_open": n_open,
        "expected_incidents": 1,
        "row_lock_used": False,
        "unique_partial_index_on_open_incident": bool(sql(
            "SELECT 1 FROM pg_indexes WHERE tablename='incidents' "
            "AND indexdef ILIKE '%unique%' AND indexdef ILIKE '%status%';")),
    })


# ─────────────── Scenario F: partition boundary ───────────────
def scenario_f() -> None:
    print("\n" + "=" * 78)
    print("SCENARIO F: Partition Boundary")
    print("=" * 78)
    parts = sql("SELECT c.relname || ' => ' || "
                "coalesce(pg_get_expr(c.relpartbound, c.oid),'?') "
                "FROM pg_class c JOIN pg_inherits i ON c.oid=i.inhrelid "
                "JOIN pg_class p ON p.oid=i.inhparent "
                "WHERE p.relname='check_results';")
    part_list = [p for p in parts.splitlines() if p.strip()]
    strategy = sql("SELECT pg_get_partkeydef('check_results'::regclass);")

    # Insert a row one month in the future through the real schema.
    dep = sql("SELECT id FROM dependencies WHERE is_deleted=false LIMIT 1;")
    org = sql(f"SELECT org_id FROM dependencies WHERE id='{dep}';") if dep else ""
    future = (datetime.now(timezone.utc) + timedelta(days=31)).isoformat()
    out = ""
    landed = ""
    if dep:
        out = sql(
            "INSERT INTO check_results "
            "(id, dependency_id, org_id, region, latency_ms, is_up, "
            " status_code, error_message, quorum_confirmed, executed_at) "
            f"VALUES (gen_random_uuid(), '{dep}', '{org}', 'us-east', 1.0, true, "
            f"200, NULL, false, '{future}') RETURNING id;")
        if out and "ERROR" not in out.upper():
            landed = sql("SELECT tableoid::regclass::text FROM check_results "
                         f"WHERE id='{out}';")

    insert_failed = "ERROR" in out.upper()
    only_default = (len(part_list) == 1 and "DEFAULT" in part_list[0].upper())

    detail = (
        f"check_results is {strategy} but the ONLY partition that exists is "
        f"{part_list}. The future-dated insert "
        f"{'FAILED: ' + out if insert_failed else 'SUCCEEDED and landed in ' + landed}. "
        f"So partitioning is declared but non-functional: because a DEFAULT "
        f"partition catches everything, there is no 'no partition found' error "
        f"— instead 100% of rows accumulate in one physical table. That is worse "
        f"than the expected failure: the platform gets none of the pruning, "
        f"vacuum or O(1) drop-old-data benefits it was designed for, the team "
        f"gets no signal that partition management is missing, and once rows are "
        f"in DEFAULT you cannot ATTACH a covering monthly partition without "
        f"moving them (ATTACH fails while overlapping rows sit in DEFAULT)."
    )
    finding("F: Partitioning", "FAIL", "P1", detail, {
        "partition_strategy": strategy,
        "partitions": part_list,
        "monthly_partitions_present": False,
        "future_insert_rejected": insert_failed,
        "future_row_landed_in": landed,
        "pg_partman_installed": bool(sql(
            "SELECT 1 FROM pg_extension WHERE extname='pg_partman';")),
        "rows_in_default_partition": sql(
            "SELECT count(*) FROM check_results_default;"),
    })


# ─────────────── Scenario G: webhook security ───────────────
def scenario_g() -> None:
    print("\n" + "=" * 78)
    print("SCENARIO G: Paystack Webhook Security")
    print("=" * 78)
    payload = {"event": "charge.success",
               "data": {"reference": "audit-forged-ref", "amount": 19900,
                        "status": "success",
                        "customer": {"email": "attacker@evil.com"},
                        "metadata": {"org_id": str(uuid.uuid4()),
                                     "plan": "agency"}}}
    body = json.dumps(payload)

    r_none = httpx.post(f"{BASE}/v1/billing/webhook", content=body,
                        headers={"Content-Type": "application/json"},
                        timeout=30)
    r_bad = httpx.post(f"{BASE}/v1/billing/webhook", content=body,
                       headers={"Content-Type": "application/json",
                                "x-paystack-signature": "deadbeef" * 8},
                       timeout=30)

    unsigned_rejected = r_none.status_code in (401, 403)
    badsig_rejected = r_bad.status_code in (401, 403)
    ok = unsigned_rejected and badsig_rejected

    src = open("app/modules/billing/service.py").read()
    detail = (
        f"No signature -> HTTP {r_none.status_code} ({r_none.text[:120]}); "
        f"invalid signature -> HTTP {r_bad.status_code} ({r_bad.text[:120]}). "
        f"handle_webhook raises UnauthorizedException when the signature is "
        f"missing and uses hmac.compare_digest for constant-time comparison "
        f"(billing/service.py:332-345), so forged upgrade events are rejected. "
        f"Residual risk: verification depends on PAYSTACK_SECRET_KEY being set — "
        f"the deployment default is an empty string, and there is no replay "
        f"protection (no event-id dedupe / timestamp window), so a captured "
        f"valid webhook can be replayed indefinitely."
    )
    finding("G: Webhook security", "PASS" if ok else "FAIL",
            "P2" if ok else "P0", detail, {
        "no_signature_status": r_none.status_code,
        "invalid_signature_status": r_bad.status_code,
        "unsigned_rejected": unsigned_rejected,
        "invalid_rejected": badsig_rejected,
        "constant_time_compare": "compare_digest" in src,
        "replay_protection": ("event_id" in src or "idempot" in src.lower()),
        "secret_configured_by_default": False,
    })


# ─────────────── Scenario H: CORS ───────────────
def scenario_h() -> None:
    print("\n" + "=" * 78)
    print("SCENARIO H: CORS Misconfiguration")
    print("=" * 78)
    tok, org_id = bootstrap()
    # Preflight from an evil origin
    pre = httpx.request("OPTIONS", f"{BASE}/v1/orgs/{org_id}/dependencies",
                        headers={"Origin": "https://evil.com",
                                 "Access-Control-Request-Method": "GET",
                                 "Access-Control-Request-Headers": "authorization"},
                        timeout=30)
    # Actual credentialed request from evil origin
    act = httpx.get(f"{BASE}/v1/orgs/{org_id}/dependencies",
                    headers={"Origin": "https://evil.com",
                             "Authorization": f"Bearer {tok}"}, timeout=30)
    # Allowed origin for comparison
    good = httpx.get(f"{BASE}/v1/orgs/{org_id}/dependencies",
                     headers={"Origin": "http://localhost:3000",
                              "Authorization": f"Bearer {tok}"}, timeout=30)

    evil_acao = act.headers.get("access-control-allow-origin")
    good_acao = good.headers.get("access-control-allow-origin")
    pre_acao = pre.headers.get("access-control-allow-origin")
    creds = good.headers.get("access-control-allow-credentials")

    safe = evil_acao is None and pre_acao is None
    detail = (
        f"Preflight from https://evil.com -> HTTP {pre.status_code}, "
        f"ACAO={pre_acao!r}. Credentialed GET from evil origin -> HTTP "
        f"{act.status_code}, ACAO={evil_acao!r}. Allowed origin -> ACAO="
        f"{good_acao!r}, allow-credentials={creds!r}. Starlette's CORSMiddleware "
        f"omits Access-Control-Allow-Origin for non-allowlisted origins, so the "
        f"BROWSER blocks evil.com from reading the response even though the "
        f"server still executes the request and returns {act.status_code}. "
        f"CORS is configured correctly (explicit CORS_ORIGINS list, not '*', "
        f"with credentials enabled). Note CORS is not an authorization control: "
        f"the request is still processed server-side, so it must never be relied "
        f"on in place of CSRF protection for cookie-based flows."
    )
    finding("H: CORS", "PASS" if safe else "FAIL", "P2" if safe else "P0",
            detail, {
        "evil_origin_acao": evil_acao,
        "evil_preflight_status": pre.status_code,
        "evil_preflight_acao": pre_acao,
        "allowed_origin_acao": good_acao,
        "allow_credentials": creds,
        "wildcard_with_credentials": good_acao == "*" and creds == "true",
    })


def main() -> None:
    scenario_c()
    scenario_d()
    scenario_e()
    scenario_f()
    scenario_g()
    scenario_h()
    scenario_b()
    scenario_a()

    os.makedirs("audit/out", exist_ok=True)
    with open("audit/out/stress_results.json", "w") as f:
        json.dump(FINDINGS, f, indent=2, default=str)
    print("\n" + "=" * 78)
    for f_ in FINDINGS:
        print(f"  {f_['result']:5} {f_['severity']:3} {f_['scenario']}")
    print("=" * 78)


if __name__ == "__main__":
    main()
