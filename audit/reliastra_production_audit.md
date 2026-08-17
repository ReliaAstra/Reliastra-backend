# Reliastra Backend — Production Readiness Audit & Remediation Roadmap

**Auditor:** Staff+ SRE (Datadog Synthetics / Stripe / UptimeRobot background)
**Date:** 2026-08-17
**Commit audited:** `3df6170` (`arena/01a01094-reliastra-backend`)
**Stack:** FastAPI + SQLAlchemy 2.0 async + PostgreSQL 15 (tested on 16.2) + Redis 7 (tested on 6.2) + Celery 5.6 + Beat + APScheduler (in-process) + MinIO + Paystack webhooks

---

## 1. Executive Summary

**Reliastra's control plane (auth, RBAC, orgs, dependencies, incidents, dashboards, evidence) is functionally complete and largely correct.** After fixing three blocking defects, the full API surface passes 76/77 functional checks against a live stack: JWT rotation, refresh-token revocation, role-based access control (viewer→403 on writes), 5-dependency check orchestration with quorum incidents, dashboards, public vendors, API-key auth, billing (against a Paystack mock), evidence generation with checksums, webhook signature rejection, and CORS enforcement all work as designed. The check pipeline correctly classifies healthy/unhealthy/timeout/SSRF-blocked dependencies and creates quorum-confirmed incidents. This is a solid MVP core.

**The data plane — the thing that must be bulletproof in a monitoring company — has three critical defects that will either corrupt data or silently lose monitoring coverage in production.** (1) The idempotency cache is namespaced only by the client-supplied key, so two tenants using the same `Idempotency-Key` get each other's cached responses — a cross-tenant data leak I reproduced deterministically (user B received user A's org object). (2) The quorum → incident path is a non-atomic read-then-write: 12 concurrent region checks created **5 incidents** for one dependency (plus a `MultipleResultsFound` crash); an incident storm is indistinguishable from a real outage. (3) The Celery worker is silently broken: `run_async()` runs each task in a fresh event loop while the asyncpg engine is process-global, producing `Task got Future attached to a different loop` errors; `schedule_checks` then returns `0` and drops the entire queue. In docker-compose this was masked because the API process runs a **second, redundant in-process scheduler** — so checks executed anyway and the broken worker was invisible. On any deployment without that fallback, zero checks would ever run.

**The rest of the audit is a standard startup-scaling backlog, plus one unpleasant surprise in schema hygiene.** The ORM defines 14 tables (admin, feedback, campaigns, sessions, announcements) and 6 `users` columns that **no migration ever created** — every endpoint touching them 500s with `relation does not exist`; I added migrations `0012–0014` to repair this. `check_results` declares `PARTITION BY RANGE` but ships with only a `DEFAULT` partition, so every row lands in one unpartitioned table (retention `DROP PARTITION` is impossible; a future-dated row is silently swallowed into the default). Each check opens a fresh `httpx.AsyncClient` (no keepalive/HTTP2), the API in-process scheduler and Celery Beat double-schedule, the worker leaks memory until OOM (measured 1.7 GB RSS in ~5 min, SIGKILL), API keys are stored as unsalted SHA-256 (GPU-brute-forceable), `timeout_seconds` is advisory (measured 5.3 s with a 3 s timeout), redirects are not followed (301 → dependency marked DOWN — fixed), and there is no metrics/tracing/structured-logging story. This report quantifies each defect and provides a P0–P3 remediation roadmap with code diffs and validation tests.

---

## 2. Environment & Method (important caveats)

Docker and Docker Hub are **unreachable from this sandbox** (only pypi.org and api.github.com are reachable egress). The stack was therefore run natively with the **real binaries**: PostgreSQL 16.2 (`pgserver` wheel bundles initdb/postgres), Redis 6.2 (`redislite` bundles redis-server), uvicorn, Celery worker + Beat, plus a Paystack API mock (port 9200) and a mock dependency-target server (port 9100). All app code is identical to the Docker images; the docker-compose topology (API + worker + beat sharing one DB/Redis) was reproduced 1:1.

| Target in the test plan | Substitution used | Reason |
|---|---|---|
| `https://httpbin.org/get` (200) | `https://api.github.com/zen` | httpbin unreachable from sandbox |
| `https://httpbin.org/status/500` | `https://api.github.com/repos/…` (404) | same platform semantics (`is_up=False`, quorum incident) |
| `https://httpbin.org/delay/15` | 760 MB wheel on `files.pythonhosted.org` + `timeout_seconds=3` | reliably slow; also exposed a **timeout-contract violation** (5.3 s > 3 s) |
| `https://httpbin.org/redirect/3` | `http://api.github.com/zen` (301→200) | same redirect class |
| `http://localhost:9999` (refused) | `http://localhost:9999/nonexistent` | SSRF protection blocks it — a finding in itself |

Two environment-specific notes: (a) httpx in this sandbox validates against certifi's CA bundle, which lacks the sandbox egress proxy CA; the API/worker were started with `SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt` (real Docker images are unaffected). (b) The sandbox has 2 CPUs / 3.9 GB RAM, which **amplified** memory defects (OOM) that would take longer to surface on real hardware — measured numbers are labelled as such.

---

## 3. Test Results

### 3.1 Step 1 — Stack startup

| # | Check | Result | Evidence |
|---|---|---|---|
| 1 | Postgres reachable, migrations `upgrade head` | ✅ PASS | 16 revisions applied (incl. new 0012–0014) |
| 2 | Redis reachable | ✅ PASS | `redis-cli ping` |
| 3 | `GET /health` | ✅ PASS | `{"status":"ok","database":"ok","redis":"ok"}` |
| 4 | OpenAPI loads | ✅ PASS | title/version correct, 89 paths |
| 5 | Celery worker connected | ✅ PASS | `Connected to redis://localhost:6379/0` |
| 6 | Celery Beat scheduling | ✅ PASS | `Sending due task schedule-checks-periodic` every 30 s |
| 7 | First `schedule_checks` executed | ✅ PASS | `Executed 0 checks across 0 dependencies` (no deps yet) |

> ⚠️ Blocking defect found during Step 1: **registration 500'd** (`column users.is_system_admin does not exist`) — the ORM was ahead of the migrations. Fixed via `0012` + `0013` (see §5, FIX-A). A second blocking defect: the **Celery worker cannot run checks at all** (`NoReferencedTableError: table 'applications'` + event-loop errors) — fixed via celery_app model imports + per-task engine reset (FIX-D).

### 3.2 Step 2 — Functional suite (live stack, 77 checks)

| Group | Pass | Fail | Key results |
|---|---|---|---|
| Auth | 7/7 | – | register 201 TokenResponse, login, refresh rotation, logout 204, revoked-token 401 |
| Orgs & RBAC | 12/12 | – | owner/admin/viewer roles; viewer POST dep → **403**; cross-tenant org access → 403; member remove → 204 |
| Dependencies & Checks | 15/16 | 1* | 5 deps created; results/history/recent populated; healthy→UP, 404→DOWN, SSRF-blocked→DOWN, **redirect 301→DOWN (bug, fixed)**, *slow timeout not tripped in sandbox (env-limited)* |
| Incidents | 4/4 | – | incident created from unhealthy dep; resolve; correlate; evidence exists |
| Dashboard | 6/6 | – | summary/latency/SLA/health/timeline/vendor-status all 200 |
| Public vendors | 5/5 | – | list + stripe detail/history/metrics/incidents (note: no pagination — see §4.10) |
| Notifications | 3/3 | – | Slack config 201; test alert 200 (delivery fails to fake webhook, correctly surfaced) |
| API keys | 8/8 | – | `full_key` returned once; no leak in list; `X-API-Key` + `Authorization: ApiKey` auth; cross-org 403; revoked key 401 |
| Billing | 2/2 | – | plan details; initialize+verify against Paystack mock |
| Evidence & verification | 4/4 | – | list/get/regenerate report; `GET /v1/verify/{id}` returns checksums |
| Security | 6/6 | – | webhook without/invalid signature → **401**; evil origin CORS blocked; configured origin allowed; **idempotency cross-tenant leak reproduced → fixed → test now passes** |
| **Total** | **76/77** | 1 | remaining failure is environment-limited (timeout test) |

*\* slow-dep: the sandbox egress serves the 760 MB file in 2–5 s, so `timeout_seconds=3` did not reliably trip; it did expose that the timeout is **soft** (one check measured 5.38 s with a 3 s timeout — httpx float timeout semantics).*

### 3.3 Step 3 — Load & stress (Scenarios A–H)

| Scenario | Expected failure | Observed | Severity |
|---|---|---|---|
| **A** Scheduler saturation (50 deps × 2 regions @ 10 s) | `schedule_checks` > 30 s, queue backup, memory growth | ✅ **Confirmed, worse than expected**: each `schedule_checks` took **53–57 s** (>30 s tick → backlog of 13–42 tasks); worker child RSS grew to **1.7 GB in ~5 min → SIGKILL (OOM)**; API process also OOM-killed (exit 137); `execute_check` tasks **starved** behind `schedule_checks` (priority inversion, 0/40 executed); worker silently returned 0 for most tasks (loop error) | **P0** |
| **B** DB pool exhaustion (100 concurrent `latency?hours=2160`) | requests timeout at 30 s | 100/100 OK in 0.7 s (pool 10+20=30, fast bounded queries). At **500 concurrent**: 500/500 OK but wall 14.3 s, **p99=12.9 s** — pool serializes hard. Forced hold of 25/30 conns for 45 s: requests still OK (queries ~0.6 s). **Exhaustion mechanism confirmed, trigger is slow queries** (unpartitioned tables at scale, scheduler-held sessions) | **P1** |
| **C** HTTP client connection overhead | new TCP per check | **Confirmed by code** (`httpx.AsyncClient` created per check, closed on scope exit → no keepalive/HTTP2): 1 TCP+TLS handshake per probe; Scenario A alone generated ~700 handshakes/240 s. Socket counters at low rate were noise (1→1 ESTAB) because the closed client releases immediately — churn is in handshakes, not open sockets | **P1** |
| **D** Idempotency collision (100 same-key POSTs) | leak if not user-scoped | Same user, same key → **1 org, 100× 201 replay** (works). **Two different users, same key → LEAK** (user B received user A's org; reproduced 4/4 runs + in suite). **Fixed** (principal-scoped key) and re-verified: no leak, same-user replay intact | **P0 fixed** |
| **E** Quorum race (1 dep × 2 regions, concurrent) | 0 or 2+ incidents | **5 incidents from 12 concurrent checks** (+ `MultipleResultsFound` crash) at the service level. Celery dispatch variant: 0/40 executed (worker starved/broken). **Fixed** (partial unique index + `ON CONFLICT` semantics): 12 concurrent → **exactly 1 incident**, 0 errors | **P0 fixed** |
| **F** Partition boundary (future-dated row) | `no partition … found for row` | With `DEFAULT` partition: insert **succeeds**, row silently lands in `check_results_default` — partitioning is **cosmetic**; all 1,517 rows in the single default partition. Without DEFAULT: exact `ERROR: no partition of relation "part_test" found for row` reproduced | **P1** |
| **G** Webhook security (no/invalid `x-paystack-signature`) | both rejected | ✅ Both **401** (`hmac.compare_digest`, SHA-512, missing-secret also 401). Paystack secret must be configured — with empty secret the endpoint rejects (safe-by-default) | PASS |
| **H** CORS (`Origin: https://evil.com` + Authorization) | blocked | ✅ Preflight from evil origin returns **no ACAO header** (blocked); configured origin gets ACAO echoed; `allow_credentials=True` with explicit origin list (correct pattern) | PASS |

### 3.4 Repo test suite (regression)

| Suite | Result |
|---|---|
| `tests/unit` | 45 passed, 4 failed — **all 4 failures pre-exist on the pristine base commit** (billing plan details, timeline flow, 2× user service pydantic) |
| `tests/integration` | 27 passed, 2 failed — **both pre-exist on the pristine base** (billing endpoints, refurbishment endpoints) |
| New/changed unit test | `test_check_and_create_incident_new` updated for atomic savepoint → passes |

**My fixes introduce zero regressions.**

---

## 4. Architectural Audit — Ratings per Dimension

### 4.1 Scheduler Architecture — **D-**
**Current:** Celery Beat every 30 s → `schedule_checks` → **inline** `execute_check` loop (`app/modules/checks/service.py:102-121`), PLUS a second APScheduler inside the API process (`app/infrastructure/scheduler.py:138-147`) started unconditionally from `app/main.py` lifespan. Two schedulers race on the shared `next_check_at` cursor; when aligned, every dependency is probed twice per tick (double egress + double writes). Because checks run inline inside one task, a single 15 s-timeout endpoint blocks the whole queue; measured task duration 53–57 s for ~100 checks vs a 30 s tick → unbounded backlog. No per-dependency backpressure, no circuit breaker, no check-due sharding.

**Fix shipped (partial):** `RUN_IN_PROCESS_SCHEDULER` flag (default true for single-container PaaS; `false` in docker-compose) — removes duplicate scheduling. **Roadmap:** Redis ZSET tick scheduler, one Celery task per check (`execute_check` already exists), per-dependency circuit breaker, staggered jitter on `next_check_at`.

### 4.2 Database Connection Management — **C-**
`pool_size=10, max_overflow=20, pool_timeout=30` (`app/db/session.py:143-146`). A single `AsyncSession` is held for the entire `schedule_checks` task (30–60 s+) while it performs ~100 checks; the request path (`get_db`) also holds a transaction for the whole request. Under concurrency the pool serializes (measured p99 12.9 s at 500 concurrent). The worker's loop-broken sessions leak as **`idle in transaction`** connections. No `max_requests`/recycling, no per-use-case pools.

### 4.3 HTTP Client Efficiency — **D**
`httpx.AsyncClient(timeout=timeout, verify=True)` created per check and closed on scope exit (`app/modules/checks/service.py:177`). No DNS cache, no TLS session reuse, no HTTP/2, no keepalive. At 10M checks/min this is 10M TCP+TLS handshakes/min. Also: `follow_redirects` defaulted to False → **any 301/302 vendor endpoint was permanently marked DOWN** (fixed). `timeout_seconds` is soft (measured 5.38 s with 3 s timeout).

### 4.4 Quorum & Incident Detection — **F → B after fix**
Read-recent-results → evaluate → write, non-atomic (`app/modules/checks/service.py:209-235`; `app/modules/incidents/service.py:83-105`). Measured: **5 incidents from 12 concurrent checks** + `MultipleResultsFound` crash. **Fix shipped:** partial unique index `uq_incidents_one_open_per_dependency` (0014) + savepoint-guarded insert returning the winner → 12 concurrent = exactly 1 incident. Remaining: quorum reads are still point-in-time; `QUORUM_WINDOW_SECONDS=60` scans unindexed partitions at scale.

### 4.5 Data Integrity (Observations dual-write) — **C-**
Every check dual-writes `check_results` + `observations` inside a savepoint that **swallows observation failures** (`app/modules/checks/service.py:55-79`) — the "immutable source of truth" can silently diverge from `check_results`, and evidence/attribution read from observations. No transactional outbox; no reconciliation job; observation write failures are log-noise. Evidence "cryptographic verification" is a **random lookup key** + SHA-256 of self-asserted content (`app/modules/evidence/service.py:224-227,264`; `app/modules/verification/router.py`) — no server-side signing, so it proves only that the stored hash matches the stored bytes, not that Reliastra produced them.

### 4.6 Partitioning Strategy — **F**
`PARTITION BY RANGE (executed_at)` declared (`0001_initial_schema.py:114`) with **only a `DEFAULT` partition** (`:117`). No monthly partitions, no `pg_partman`, no management. All rows land in `check_results_default` (verified: 100% of rows). Future-dated rows are silently absorbed instead of failing. Retention (`DROP PARTITION`) is impossible; partition pruning never happens; at 10M checks/min the default partition becomes a hot monolith.

### 4.7 Celery Worker Design — **F**
Sync Celery tasks call async code through `run_async()` (`app/modules/checks/tasks.py:11-31`) — a new event loop per task against a process-global asyncpg engine → `Task got Future attached to a different loop`, `coroutine Connection._cancel was never awaited`, **silent return 0**, unbounded memory growth (1.7 GB RSS → OOM SIGKILL), and cross-loop pool corruption. The worker also lacked the full model metadata (`NoReferencedTableError: applications`) so even a healthy loop couldn't flush. **Fix shipped:** import all model modules in `celery_app.py`; `reset_engine()` per task (one pool per loop, disposed). **Roadmap:** arq (native async task queue) or sync SQLAlchemy in Celery.

### 4.8 Security — **B-**
Good: bcrypt passwords, JWT rotation + revocation via DB, per-org RBAC, SSRF guard (blocks private/link-local incl. cloud metadata), webhook HMAC (sha-512, `compare_digest`), CORS with explicit origins + credentials, API-key scopes enforced. Weaknesses: API keys stored as **unsalted SHA-256** (`app/core/security.py:86-88`) — GPU-brute-forceable at ~10⁹/s; rate limiters **fail open** on Redis errors (`app/core/rate_limit.py` — auth endpoints become unlimited during a Redis outage); no JWT `iss`/`aud`; webhook signature optional header is the only gate (good) but HMAC secret shares the app SECRET_KEY config space; no header whitelist on outbound checks (customer-supplied headers pass through — `Host`/`Authorization` injection into the probe).

### 4.9 Observability — **D**
No metrics endpoint, no OpenTelemetry, no structured JSON logging; only `X-Request-ID` passthrough. During the OOM incidents there was no metric to page on. `/health` opens a DB connection + Redis ping on every call (`app/main.py:204-231`) — a health-check storm amplifies DB load.

### 4.10 Operational Excellence — **C-**
Migrations run in the API container command (`alembic upgrade head` in docker-compose) — two API replicas racing migrations cause split-brain; no `/health/live` vs `/health/ready`; public vendor list has **no pagination** (returns all 5 seeded; will be unbounded); `GET /v1/public/vendors/stripe/history` returns fabricated 100% uptime with zero observations (`recent_checks_count: 0` → still 100%) — dashboard/API trust empty aggregates; seed vendors are hardcoded rows with `last_check_at: null` presented as if live.

---

## 5. Remediation Roadmap

Priorities: **(1) data integrity, (2) security, (3) scalability, (4) cost.** Every item has file:line, before/after code, expected impact, and a validation test. Items marked **FIXED** were implemented and verified in this session.

---

### P0 — Fix This Week

#### P0-1 · FIXED — Idempotency cache is a cross-tenant data leak
`app/main.py:80` (pre-fix)

```python
# BEFORE  — global namespace: tenant B replays tenant A's cached response
cache_key = f"idempotency:{idempotency_key}"
```

```python
# AFTER — principal-scoped namespace (JWT sub / API-key digest / client IP)
def _idempotency_principal(request: Request) -> str:            # app/main.py:73
    import hashlib
    auth = request.headers.get("authorization", "")
    api_key = request.headers.get("x-api-key", "")
    if auth.lower().startswith("bearer "):
        token = auth.split(None, 1)[1].strip()
        try:
            from app.core.security import decode_token
            return f"user:{decode_token(token).get('sub', 'unknown')}"
        except Exception:
            return "user:invalid-token"
    credential = api_key or (auth if auth.lower().startswith(("apikey ", "rel_")) else "")
    if credential:
        return "key:" + hashlib.sha256(credential.encode()).hexdigest()[:32]
    client = request.client
    return f"ip:{client.host if client else 'unknown'}"

# inside IdempotencyMiddleware.dispatch
principal = self._idempotency_principal(request)                 # app/main.py:110
cache_key = f"idempotency:{principal}:{idempotency_key}"         # app/main.py:111
```

**Impact:** eliminates cross-tenant response replay (data leak → no leak). Same-user replay (the point of idempotency) preserved; token rotation invalidates a key in flight — acceptable. **Test:** two users, same key, POST /v1/orgs → different orgs; same user twice → same org (implemented in `audit/functional_tests.py`, now passing; manual 4/4 reproduction of the leak before fix).

#### P0-2 · FIXED — Quorum → incident race creates duplicate incidents
`app/modules/incidents/service.py:83-105` (pre-fix read-then-write) → now atomic.

```sql
-- migration 0014_open_incident_unique.py
CREATE UNIQUE INDEX uq_incidents_one_open_per_dependency
    ON incidents (org_id, dependency_id) WHERE status = 'open';
```

```python
# BEFORE (service)
existing = await self.repository.get_open_for_dependency(session, dependency_id)
if existing:
    return existing
incident = await self.repository.create(...)   # two sessions both pass the check
await self.correlation_strategy.correlate(session, incident)

# AFTER (service) — savepoint-guarded insert; loser returns winner
from sqlalchemy.exc import IntegrityError
try:
    async with session.begin_nested():
        incident = await self.repository.create(...)
        await session.flush()
except IntegrityError:
    incident = await self.repository.get_open_for_dependency(session, dependency_id)
    if incident:
        logger.info("Lost incident creation race for dep %s", dependency_id)
        return incident
    raise
```

Plus `app/modules/incidents/repository.py:41-53`: `scalar_one_or_none()` → `scalars().first()` (legacy duplicates no longer crash quorum evaluation). **Impact:** exactly one open incident per dependency under concurrency (measured 5 → 1 from 12 concurrent checks); `MultipleResultsFound` crash eliminated. **Test:** service-level 12-concurrent `execute_check` on a failing dep → `SELECT count(*) FROM incidents WHERE status='open'` = 1 (implemented; also covered by updated `tests/unit/test_incident_service.py`).

#### P0-3 · FIXED — Celery worker silently drops every task (checks never run)
`app/modules/checks/tasks.py:11-31` + `app/db/session.py`.

```python
# app/db/session.py — new
def reset_engine() -> None:
    """asyncpg connections are loop-bound; each Celery task runs on a fresh
    loop, so the shared engine must not outlive the task's loop."""
    global _engine, _sessionmaker
    engine = _engine
    _engine = None
    _sessionmaker = None
    if engine is not None:
        try:
            asyncio.run(engine.dispose())
        except Exception:
            logger.debug("engine dispose during reset failed", exc_info=True)

# app/modules/checks/tasks.py — wrap both tasks
try:
    return run_async(_run())
finally:
    from app.db.session import reset_engine
    reset_engine()
```

Also `app/infrastructure/celery_app.py`: import **all** model modules (worker previously failed `NoReferencedTableError: applications` on any flush). **Impact:** worker executes every `schedule_checks` (measured 102 then 104 checks on consecutive tasks — previously the 2nd+ returned 0), memory stays bounded instead of 1.7 GB → OOM, `execute_check` tasks become dispatchable. **Test:** send 3 `schedule_checks` tasks back-to-back → each produces results rows (verified); assert no `attached to a different loop` in worker log.

#### P0-4 · FIXED — Schema drift: ORM ahead of migrations (registration 500)
New migrations `0012_user_admin_fields` (6 `users` columns) and `0013_missing_model_tables` (14 tables from `app/modules/admin/models.py` etc. — admin_audit_logs, announcements, app_error_logs, email_campaigns, feedback_tickets, in_app_notifications, plan_change_histories, system_health_alerts, user_activity_logs, user_sessions, announcement_dismissals, email_campaign_recipients, feedback_messages, in_app_notification_deliveries). **Impact:** register/login no longer 500; admin/feedback/campaign endpoints stop returning `relation does not exist`. **Test:** `alembic upgrade head` on a fresh DB + `alembic check` (no diff) + register user (all verified). **Process fix (P2):** add `alembic check` to CI and autogenerate drift detection.

#### P0-5 · Add a transactional outbox for observations (design, not yet coded)
`app/modules/checks/service.py:55-79` currently swallows observation failures. Replace the dual-write with a same-transaction outbox row + dispatcher, or (minimal) make observation failure fail the check and add a reconciliation job:

```python
# BEFORE
async with session.begin_nested():
    await observation_service.record_observation(...)
except Exception as exc:
    logger.warning("Failed to record observation ...")   # silent divergence

# AFTER (minimal)
await observation_service.record_observation(...)          # no savepoint, no swallow
# + nightly reconciliation: rows in check_results without an observation
#   row (same (source_id, timestamp)) are backfilled; mismatches alert.
```

**Impact:** observations (the "immutable source of truth" feeding evidence/attribution/SLA) can no longer silently diverge from check results. **Test:** unit — force `record_observation` to raise → check insert rolls back; integration — delete an observation row, run reconciliation, assert backfill + alert.

---

### P1 — Fix This Month

#### P1-1 · One Celery task per check + Redis ZSET scheduler
Replace the inline loop in `schedule_due_checks` (`app/modules/checks/service.py:102-121`) with queueing:

```python
# AFTER (service) — dispatch, don't execute
async def schedule_due_checks(self, session) -> int:
    due = await self.dep_repository.get_due_dependencies(session)
    for dep in due:
        dep.next_check_at = now + timedelta(seconds=dep.check_interval_seconds)
        for region in (dep.regions or ["us-east", "eu-west"]):
            execute_check.delay(str(dep.id), region)   # one task per probe
    await session.flush()
    return len(due) * len(regions)
```

`execute_check` already exists as a Celery task (`app/modules/checks/tasks.py:51`) — it just never gets used. For sub-30 s granularity, move the due-cursor to a Redis ZSET (`zadd checks:due {next_check_at} dep_id`) scanned by a 5 s beat tick, instead of polling `next_check_at` every 30 s. **Impact:** removes the 53–57 s task pile-up; a slow endpoint no longer blocks other deps; per-probe retries/circuit breakers become possible. **Test:** load Scenario A — `schedule_checks` task duration < 5 s; queue depth stable; no starvation of `execute_check`.

#### P1-2 · FIXED — Follow redirects in the check engine
`app/modules/checks/service.py:177-191`:

```python
# BEFORE
async with httpx.AsyncClient(timeout=timeout, verify=True) as client:

# AFTER
async with httpx.AsyncClient(timeout=timeout, verify=True,
                             follow_redirects=True, max_redirects=5) as client:
```

**Impact:** 301/302 vendor endpoints (http→https, www, CDN) stop being marked DOWN permanently. **Test:** dep pointing at `http://api.github.com/zen` → `is_up=True, status_code=200` (verified). Redirect loops still fail (max_redirects → `TooManyRedirects` → is_up=False).

#### P1-3 · Global HTTP connection pool (keepalive + HTTP/2)
`app/modules/checks/service.py` — hoist the client:

```python
# app/infrastructure/http_pool.py (new)
import httpx
_client: httpx.AsyncClient | None = None
async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        limits = httpx.Limits(max_connections=200, max_keepalive_connections=50)
        _client = httpx.AsyncClient(limits=limits, http2=True,
                                    follow_redirects=True, max_redirects=5,
                                    timeout=httpx.Timeout(10.0))
    return _client
# execute_check: client = await get_client(); response = await client.request(...)
```

**Impact:** amortizes DNS+TLS+TCP across probes (10M handshakes/min → ~50 keepalive sockets per region); HTTP/2 multiplexing; lower p95. **Test:** Scenario C — count `TIME_WAIT` sockets while running 100 probes against a local target; with the pool, TIME_WAIT stays near zero.

#### P1-4 · Partitioning that actually partitions
Replace the single DEFAULT partition with real monthly ranges + automated creation:

```sql
-- migration 0015: create monthly partitions going forward
DO $$
DECLARE m date;
BEGIN
  FOR m IN SELECT generate_series(date_trunc('month', now())::date,
                                  date_trunc('month', now())::date + interval '3 months',
                                  interval '1 month')
  LOOP
    EXECUTE format(
      'CREATE TABLE IF NOT EXISTS check_results_%s PARTITION OF check_results
       FOR VALUES FROM (%L) TO (%L)',
      to_char(m, 'YYYYMM'), m, m + interval '1 month');
  END LOOP;
END $$;
-- + cron: every month, create next partition, drop partitions older than
--   plan retention (PLAN_RETENTION_DAYS) — the *reason* for partitioning.
```

Adopt `pg_partman` (community standard) or a small Alembic revision generator. **Impact:** partition pruning on time-window queries; retention becomes `DROP PARTITION` (instant) instead of `DELETE` (VACUUM pressure); future-dated rows now error loudly instead of silently joining the default. **Test:** insert with `executed_at = now()+1mo` → row lands in `check_results_YYYYMM`; `DROP PARTITION` older than retention removes rows in ms.

#### P1-5 · Pool isolation & recycling
`app/db/session.py:143-146`: add `pool_recycle=300` (asyncpg idle timeout ~5 min), `max_requests=1000`, and give the scheduler its own engine (small pool) so long-held scheduler sessions can't starve the API pool:

```python
engine_kwargs.update(pool_pre_ping=True, pool_size=10, max_overflow=20,
                     pool_timeout=30, pool_recycle=300, max_requests=1000)
# scheduler: create_async_engine(url, pool_size=2, max_overflow=4) — separate
```

**Impact:** no stale-idle connections, no unbounded checkout queues; scheduler holds can no longer consume the API pool. **Test:** Scenario B at 500 concurrent — p99 < 2 s; pg `idle in transaction` count stays 0.

#### P1-6 · Argon2id for API keys (stop GPU brute force)
`app/core/security.py:86-88`:

```python
# BEFORE
def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()

# AFTER (uses argon2-cffi; store "argon2$v=19$m=65536,t=3,p=4$<salt>$<hash>")
def hash_api_key(key: str) -> str:
    from argon2 import PasswordHasher
    return PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4).hash(key)
# lookup by raw key is impossible => store <prefix> + <hash> and verify by
# scanning the org's keys (bounded by count) or maintain a keyed-HMAC index.
```

**Impact:** offline brute force of a leaked key DB goes from ~10⁹ guesses/s to ~10²/s per key. **Test:** unit — same key hashes differently each call (salt), verify returns True, wrong key False.

#### P1-7 · Hard timeout enforcement in probes
`app/modules/checks/service.py` — replace the float timeout with an explicit per-phase contract and a hard deadline:

```python
timeout = httpx.Timeout(
    connect=5.0, read=float(dep_dto.timeout_seconds), write=5.0, pool=5.0,
    # no `total` — read timeout must be a hard cap per response-chunk wait
)
```

If the platform truly needs a total wall-clock cap, enforce it with `asyncio.wait_for` around the request and record `timeout=total`. **Impact:** `timeout_seconds` becomes a promise (measured violation 5.38 s vs 3.0 s eliminated). **Test:** local slow target (mock server) — assert check fails at ≤ timeout_seconds + 500 ms.

---

### P2 — Fix This Quarter

#### P2-1 · Prometheus /metrics + OpenTelemetry + structured logs
Add `/metrics` (prometheus-client, RED/Four-Golden-Signals per endpoint: request rate, error rate, latency histogram, saturation for pool/queue), OpenTelemetry spans for check execution + DB queries, JSON logs with `request_id` (already generated) + `org_id` + `dependency_id`:

```python
# app/core/metrics.py (new)
from prometheus_client import Counter, Histogram, Gauge
CHECKS_TOTAL = Counter("reliastra_checks_total", "...", ["org_id", "dependency_id", "region", "outcome"])
CHECK_LATENCY = Histogram("reliastra_check_latency_seconds", "...", ["region"])
DB_POOL_IN_USE = Gauge("reliastra_db_pool_in_use", "...")
QUEUE_DEPTH = Gauge("celery_queue_depth", "...")
# FastAPI middleware: histogram per route; BaseHTTPMiddleware per request id in logs
```

**Impact:** OOMs and queue backlogs become pages, not post-mortems. **Test:** hit `/metrics`, assert `reliastra_checks_total` increments after a check; alert rule unit test on QUEUE_DEPTH > 10.

#### P2-2 · Split health endpoints + stop migrations in the app container
`app/main.py:204-231`: add `/health/live` (process alive, no dependencies) and `/health/ready` (DB + Redis). docker-compose `api` command: run `alembic upgrade head` in an **init container / separate job**, then `uvicorn` with `--no-migrate`. **Impact:** removes split-brain migrations with 2+ API replicas; removes DB-load-on-every-liveness-probe; readiness gates LB routing correctly.

#### P2-3 · Pagination on public vendors (and all list endpoints)
`app/modules/vendors/router.py:32` returns a bare list. Add `limit`/`offset`/`cursor` (the repo already has `app/core/pagination.py` — use it) and a `total` envelope or `Link` headers. **Impact:** prevents unbounded payloads as the vendor catalog grows; matches Stripe-style API conventions. **Test:** seed 50 vendors, assert page size respected and cursor stable under writes.

#### P2-4 · CI drift gate
`.github/workflows/ci.yml`: add `alembic check` (fails when models ≠ migrations) and a schema-dump diff job. **Impact:** the P0-4 class of bug (models ahead of migrations) can never silently ship again. **Test:** CI fails on any model change without a migration.

#### P2-5 · Rate limiter fail-closed for auth, fail-open only for read-only public endpoints
`app/core/rate_limit.py`: auth routes (`/v1/auth/*`, `/v1/billing/webhook`) should reject (429) when Redis is unavailable rather than open the door; public GET endpoints may stay fail-open. **Impact:** a Redis outage no longer turns off brute-force protection. **Test:** stop Redis, assert `/v1/auth/login` returns 503/429; `/v1/public/vendors` still 200.

#### P2-6 · Header whitelist on outbound checks + secret redaction
`app/modules/dependencies/schemas.py:35-41` already blocks some headers; extend to strip `Host`, `Authorization`, `Cookie`, `Proxy-*` and redact stored header values in API responses. **Impact:** closes header-injection/credential-exfiltration via customer-defined headers. **Test:** create dep with `Host: internal.corp` → check request is blocked/scrubbed.

---

### P3 — Strategic (10× scale)

#### P3-1 · Replace Celery `run_async` with arq (or sync SQLAlchemy in Celery)
Keep Python/FastAPI; swap the broker task layer: arq runs native async tasks in a single event loop (no loop-mismatch class of bugs at all), supports cron/retries/backpressure natively. Migration path: keep the `execute_check`/`schedule_checks` contract, swap `celery_app` for `arq` worker; docker-compose replaces `celery` commands with `arq app.infrastructure.arq_app.WorkerSettings`. **Impact:** removes the entire F-rated worker dimension; memory stays flat; asyncpg pool reuse is valid. **Test:** soak 10 min at Scenario A load — RSS stable, zero "different loop" errors.

#### P3-2 · Signed evidence (real cryptographic verification)
Replace bearer-lookup verification with an Ed25519 signature over the canonical evidence JSON:

```python
# app/modules/evidence/service.py (after data_hash computation)
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
signature = priv.sign(canonical_bytes)          # key from KMS/env
# verification endpoint: verify(pub, canonical_repr, signature) — no DB trust
```

**Impact:** evidence becomes verifiable by third parties (auditors/SLA disputes) without trusting our DB; hash-chaining across incident snapshots gives tamper-evidence over time. **Test:** mutate a stored observation → verification fails; re-signing without the private key is impossible.

#### P3-3 · Regional check architecture (quorum as first-class routing)
Move probes to per-region workers/egress (the `region` field already exists), evaluate quorum in a central aggregator via Redis `SADD checks:failure:{dep}` + `SCARD` (or the atomic incident upsert from P0-2). Regional network partitions then surface as per-region degradation instead of false incidents. **Test:** Scenario E with region A blocked — one region degrades, quorum not met, no incident; both blocked — exactly one incident.

#### P3-4 · Time-series compaction for dashboards
The latency/uptime queries scan observation rows per request (`dashboard/router.py:36-58`, limit 500). At 10M checks/min, pre-aggregate into hourly/daily rollups (or TimescaleDB continuous aggregates — permitted: same PostgreSQL engine). **Impact:** dashboard queries stay O(buckets) not O(rows); SLA math is reproducible from rollups. **Test:** 1M-row fixture, dashboard p99 < 100 ms.

---

## 6. Fixes Shipped in This Session (with verification)

| Fix | Files | Verified |
|---|---|---|
| Schema drift repair | `0012_user_admin_fields.py`, `0013_missing_model_tables.py` | register/login 201; 14 tables + 6 columns exist; `alembic current` = head |
| Worker metadata completeness | `app/infrastructure/celery_app.py` | 52 tables in metadata incl. `applications`; worker flush succeeds |
| Idempotency principal scoping (P0 leak) | `app/main.py:73-111` | cross-user same key → different orgs; same-user replay intact |
| Quorum atomicity (P0 race) | `0014_open_incident_unique.py`, `incidents/service.py:104-133`, `incidents/repository.py:41-53` | 12 concurrent checks → exactly 1 incident (was 5 + crash) |
| Worker loop/engine isolation (P0 silent drop) | `app/db/session.py:199-218`, `checks/tasks.py` | consecutive tasks execute 102/104 checks; no loop errors; RSS bounded |
| Redirects followed | `checks/service.py:177-191` | 301 dep → `is_up=True, status=200` (was DOWN) |
| Redundant scheduler removed in compose | `config.py:123`, `main.py:166-168`, `docker-compose.yml` | Beat is the sole scheduler; single-container PaaS still supported |
| Interval schema floor relaxed | `dependencies/schemas.py:21,53` | professional 5 s intervals no longer blocked by Pydantic `ge=10` |

## 7. Appendix — Test Scripts

All scripts are in the repo under `audit/` and their JSON artifacts under `audit/results/`:

- **`audit/functional_tests.py`** — full API-surface suite (77 checks: auth, RBAC, dependencies, checks, incidents, dashboards, public vendors, notifications, API keys, billing, evidence, verification, webhook security, CORS, idempotency). Run: `python audit/functional_tests.py` → `audit/results/functional_results.json`.
- **`audit/load_tests.py`** — Scenarios A–F. Run per scenario: `python audit/load_tests.py a|b|c|d|e|f` → `audit/results/load_results.json` (consolidated: `load_results_consolidated.json`).
- **`audit/mock_target_server.py`** — local dependency-target emulator (200/500/delay/redirect) for direct probe testing.
- **`audit/mock_paystack.py`** — Paystack API mock for billing flows.

Key assertions (excerpts):

```python
# Idempotency cross-tenant leak (now passes)
r1 = req("POST", "/v1/orgs", json={"name": "Idem A"}, headers={**bearer(owner_tok), "Idempotency-Key": key})
r2 = req("POST", "/v1/orgs", json={"name": "Idem B"}, headers={**bearer(viewer_tok), "Idempotency-Key": key})
assert r1.json()["id"] != r2.json()["id"], "cross-tenant idempotency leak"

# Quorum race (now 1 incident)
results = await asyncio.gather(*[execute_check(session, dep, region) for _ in range(12)])
assert count_open_incidents(dep) == 1

# Redirect handling (now UP)
async with httpx.AsyncClient(timeout=10, verify=True, follow_redirects=True, max_redirects=5) as c:
    r = await c.get("http://api.github.com/zen")
assert r.status_code == 200 and r.history  # followed 301
```

Environment bootstrap (sandbox where Docker Hub is blocked):

```bash
python3 -m venv venv && venv/bin/pip install -r requirements.txt pgserver redislite
venv/bin/python -c "import pgserver; pgserver.get_server(...)"   # real PostgreSQL 16
venv/lib/python3.11/site-packages/redislite/bin/redis-server --port 6379
venv/bin/alembic upgrade head
SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt venv/bin/uvicorn app.main:app --port 8000
```
