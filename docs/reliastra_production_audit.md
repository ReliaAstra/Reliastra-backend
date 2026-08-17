# Reliastra Backend — Production Readiness Audit

**Auditor:** Founding Production Engineer (Staff+ SRE)
**Date:** 2026-08-16
**Commit audited:** `0b99514` — *feat: replace Celery with APScheduler in-process scheduler*
**Branch:** `arena/01a00cdd-reliastra-backend`
**Verdict:** 🟠 **NOT PRODUCTION READY** — 3 P0 data-integrity/security defects, 5 P1 scalability defects.

---

## Executive Summary

Reliastra is a well-structured modular monolith. The domain decomposition (26 modules, each with `models / repository / service / router / schemas`) is disciplined, the RBAC model is correctly enforced at the router layer, and multi-tenant isolation held under every probe I threw at it — cross-tenant reads returned `403`, API-key revocation took effect immediately, refresh-token rotation invalidated the predecessor, and Paystack webhook signatures are verified with `hmac.compare_digest` before any billing mutation. 60 of 67 functional assertions passed. This is a materially better security baseline than most seed-stage platforms, and the team deserves credit for it.

**However, the platform has a critical correctness flaw at the exact point where it makes its money: incident detection.** The quorum evaluator in `app/modules/checks/service.py` performs a read-evaluate-write cycle with no row lock and no uniqueness constraint. Across 15 controlled trials of simultaneous two-region failure, it produced the correct single incident only **13/15 times (87%)** — 2 trials silently produced **zero** incidents for a hard-down dependency. Under higher contention it fails the other direction and inserts **duplicate** open incidents, which then permanently bricks that dependency: `IncidentRepository.get_open_for_dependency()` uses `scalar_one_or_none()`, so from the moment duplicates exist, *every subsequent check for that endpoint throws `MultipleResultsFound` forever*. I captured hundreds of these in the running server's logs. The customer sees a monitor that has silently stopped monitoring, and an incident that can never auto-resolve. This is the single most important finding in the report.

**That same failure path silently corrupts the evidence chain Reliastra sells as "cryptographic verification."** `_record_observation()` is invoked as the *last* statement of `execute_check()`, after incident handling. When incident handling raises, the `check_result` row is already committed but the observation never is. I measured the divergence on live data: **2,080 `check_results` vs 2,039 `observations`**, and on the specific dependencies hit by the quorum race, **46 `check_results` produced only 5 `observations` — 89% loss**. Every orphan was a `quorum_confirmed=true` failure, i.e. precisely the outage records an evidence report exists to prove. Since `EvidenceService.generate_for_incident()` hashes the *observations* table (`data_hash = sha256(canonical_bytes)`), Reliastra is issuing SHA-256-signed PDFs that faithfully attest to demonstrably incomplete data. The cryptography is sound; the input is not. A customer using one of these reports in an SLA credit dispute would be presenting an under-count of their vendor's downtime. I also confirmed a **cross-tenant idempotency leak** (user B replaying user A's `Idempotency-Key` received user A's organization object verbatim, HTTP 201) and that the declared `PARTITION BY RANGE` on `check_results` has exactly one `DEFAULT` partition, so 100% of rows land in a single physical table with none of the intended pruning benefits.

On scalability the news is better than feared but still limiting. The scheduler is **serial by construction**: one APScheduler job, `max_instances=1`, awaiting every probe inline in a nested `for dep / for region` loop over a single shared `AsyncSession`. With 50 dependencies × 2 regions I measured a **35.1s** full cycle against a 30s beat and **30% of nominal throughput** (900 of 3,000 expected results in 5 minutes) — and because dispatch is tied to the 30s beat, **any `check_interval_seconds` below 30 is silently ignored**, which means the 5s and 15s intervals sold on the Professional/Agency tiers are not delivered. Notably the connection pool did *not* collapse under 100 concurrent 90-day dashboard queries (100/100 succeeded, p95 2.47s) because that serial scheduler only ever holds one connection; fixing the scheduler concurrency without simultaneously raising `pool_size` will convert finding A into finding B. Fix order matters, and the roadmap below reflects that.

### Fixes already applied during this audit

| File | Defect | Status |
|---|---|---|
| `app/db/migrations/env.py:100` | `connect_args=None` → `TypeError`, **all migrations failed on any non-SSL deploy** (the default compose path) | ✅ Fixed |
| `app/infrastructure/storage.py:141` | `except self._boto3_client.exceptions...` → `AttributeError` on the minio path, **crashed all evidence generation (HTTP 500)** | ✅ Fixed |
| `app/db/migrations/env.py:67`, `tests/conftest.py:43` | Unescaped `%` in DB URL → `ValueError: invalid interpolation syntax`, **entire test suite unrunnable (79 collection errors)** | ✅ Fixed — suite now runs 73 passed / 6 pre-existing failures |

---

## Test Environment

Docker is unavailable in this sandbox and the Debian mirrors are unreachable, so rather than simulate, I built the real dependency stack from source and ran the actual application against it:

| Component | How it was provisioned | Version |
|---|---|---|
| PostgreSQL | `pgserver` wheel, managed via `pg_ctl`, TCP on `127.0.0.1:5432` | **16.2** |
| Redis | compiled from upstream source (`make MALLOC=libc`) | **7.2.5** |
| S3 / MinIO | `moto.server` (S3-compatible) on `:9000` | latest |
| API | real `uvicorn app.main:app` on `0.0.0.0:8000`, in-process APScheduler live | commit `0b99514` |
| Migrations | real `alembic upgrade head` — all 15 revisions applied | — |

`GET /health` → `{"status":"ok","checks":{"database":"ok","redis":"ok"}}`; `GET /openapi.json` → **88 paths**.

> **Note on the stack topology.** The task described Celery + Beat containers, but commit `0b99514` **replaced Celery with an in-process APScheduler** (`app/infrastructure/scheduler.py`) running inside the uvicorn event loop. `docker-compose.yml` still defines `celery-worker` and `celery-beat` services pointing at `app.infrastructure.celery_app`, and `app/modules/*/tasks.py` still exist. **The compose file and the application have diverged** — this is itself a P1 operational finding (§O-1). I audited what the code actually runs.
>
> **Note on probe targets.** Sandbox egress is allowlisted; `httpbin.org` is unreachable. I substituted equivalent reachable endpoints (`api.github.com/status` = healthy, `api.github.com/<404>` = failing, `http://pypi.org` = redirect). Early TLS errors in the logs were an environment CA-bundle issue (`SSL_CERT_FILE`), **not** an application defect — I corrected it and re-ran. The `localhost:9999` connection-refused case was correctly rejected by the app's own SSRF guard, which is working as designed.

---

## Test Results

### Functional (60/67 passed)

| # | Area | Test | Result | Sev |
|---|---|---|---|---|
| 1 | Auth | `POST /register` → 201, TokenResponse shape | ✅ PASS | — |
| 2 | Auth | `POST /login` issues new tokens | ✅ PASS | — |
| 3 | Auth | `POST /refresh` rotates token | ✅ PASS | — |
| 4 | Auth | Old refresh token revoked after rotation (replay → 401) | ✅ PASS | — |
| 5 | Auth | Wrong password → 401 | ✅ PASS | — |
| 6 | Auth | `POST /logout` → 204 | ✅ PASS | — |
| 7 | Auth | Refresh revoked after logout → 401 | ✅ PASS | — |
| 8 | Org | `POST /v1/orgs` → 201 | ✅ PASS | — |
| 9 | Org | `GET /v1/orgs` lists orgs | ✅ PASS | — |
| 10 | Org | Creator role exposed as `owner` in list payload | ❌ **FAIL** | P2 |
| 11 | RBAC | Invite member → 201 | ✅ PASS | — |
| 12 | RBAC | **Viewer cannot POST dependencies → 403** | ✅ PASS | — |
| 13 | RBAC | Viewer can read → 200 | ✅ PASS | — |
| 14 | RBAC | `PATCH` member role → admin | ✅ PASS | — |
| 15 | RBAC | **Cross-tenant dependency read → 403** | ✅ PASS | — |
| 16 | RBAC | **Cross-tenant dashboard read → 403** | ✅ PASS | — |
| 17–21 | Deps | Create all 5 dependency archetypes → 201 | ✅ PASS | — |
| 22 | Security | Create-time SSRF validation on `endpoint_url` | ❌ **FAIL** | P1 |
| 23 | Deps | `GET /dependencies` → 5 | ✅ PASS | — |
| 24 | Checks | Scheduler executed checks within 150s | ✅ PASS | — |
| 25 | Checks | `GET /results`, `/history` aggregation | ✅ PASS | — |
| 26 | Checks | `GET /checks/recent` | ✅ PASS | — |
| 27 | Checks | Redirect chain recorded (302 not followed) | ❌ **FAIL** | P1 |
| 28 | Incidents | 500-dependency created an incident | ✅ PASS | — |
| 29 | Incidents | `GET /incidents/{id}/evidence` → 200 | ✅ PASS¹ | — |
| 30 | Incidents | `POST /correlate` (schema `correlated_dependency_id`) | ✅ PASS | — |
| 31 | Incidents | `PATCH` resolve → 200 | ✅ PASS | — |
| 32–37 | Dashboard | summary, latency, sla-degradation, dependency-health, incident-timeline, vendor-status | ✅ PASS | — |
| 38 | Dashboard | `hours=2160` accepted (8–35ms) | ✅ PASS | — |
| 39 | Dashboard | `hours=999999` → 422 | ✅ PASS | — |
| 40 | Vendors | `GET /public/vendors` → 200 | ✅ PASS | — |
| 41 | Vendors | Vendor list is paginated | ❌ **FAIL** | P1 |
| 42–45 | Vendors | stripe detail / history / metrics / incidents | ✅ PASS | — |
| 46 | Notify | Create Slack config → 201 | ✅ PASS | — |
| 47 | Notify | `POST /notifications/test` → 200 | ✅ PASS | — |
| 48 | ApiKeys | `full_key` returned exactly once on create | ✅ PASS | — |
| 49 | ApiKeys | **List does NOT leak `full_key`** | ✅ PASS | — |
| 50 | ApiKeys | `Authorization: ApiKey rel_...` works | ✅ PASS | — |
| 51 | ApiKeys | `X-API-Key` header works | ✅ PASS | — |
| 52 | ApiKeys | **Revoked key rejected → 401** | ✅ PASS | — |
| 53 | Billing | `GET /billing/plan` reflects tier limits | ✅ PASS | — |
| 54 | Billing | `initialize` / `verify` fail closed when unconfigured | ✅ PASS | — |
| 55–58 | Evidence | list / get / regenerate / `GET /v1/verify/{id}` | ✅ PASS¹ | — |
| 59 | Evidence | **`/v1/verify/{unknown}` returns HTTP 200** (body `found:false`) | ❌ **FAIL** | P2 |
| 60 | Evidence | Evidence auto-generated for incident | ✅ PASS¹ | — |

¹ Passes **only after** the `storage.py` fix applied during this audit; previously HTTP 500.

### Load & Stress (Scenarios A–H)

| Scenario | Result | Sev | Measured outcome |
|---|---|---|---|
| **A** Scheduler saturation | ❌ **FAIL** | P1 | 50 deps × 2 regions: **900/3000 results (30%)**, full cycle **35.1s** vs 30s beat. Sub-30s intervals silently ignored. |
| **B** DB pool exhaustion | ✅ PASS | P1 | 100 concurrent `hours=2160`: **100/100 OK**, p50 1645ms / p95 2466ms, peak 38 PG conns. Survives *because* the scheduler is serial. |
| **C** HTTP connection churn | ❌ **FAIL** | P1 | New `AsyncClient` per probe. **263ms vs 224ms pooled → 15–31% of reported `latency_ms` is handshake, not vendor latency.** No HTTP/2, no keepalive. |
| **D** Idempotency collision | ❌ **FAIL** | **P0** | 200 concurrent same-key POSTs → **3 distinct orgs, 4 DB rows**. **Cross-tenant replay confirmed: user B got user A's org, HTTP 201.** |
| **E** Quorum race | ❌ **FAIL** | **P0** | 15 trials → **87% correct**, 2 **missed** incidents; under contention **duplicate** incidents that permanently brick the dependency. |
| **F** Partitioning | ❌ **FAIL** | P1 | `RANGE (executed_at)` declared; **only `check_results_default` exists**. Future-dated insert lands in DEFAULT. No `pg_partman`. |
| **G** Webhook security | ✅ PASS | P2 | Unsigned → **401**; bad signature → **401**; `hmac.compare_digest` used. Residual: no replay protection. |
| **H** CORS | ✅ PASS | P2 | `evil.com` receives **no** `Access-Control-Allow-Origin`; allowlist explicit, not `*`. |

---

## Architectural Findings

| # | Dimension | Grade | One-line justification |
|---|---|---|---|
| 1 | Scheduler architecture | **D** | Serial inline loop, `max_instances=1`, 35s cycle at 50 deps; sub-30s intervals unhonoured; no backpressure or circuit breaker. |
| 2 | DB connection management | **C** | One session spans an entire multi-minute cycle; pool 10+20 will not absorb the scheduler fix. Held up under test only due to serialism. |
| 3 | HTTP client efficiency | **D** | Per-probe client; 15–31% latency inflation; no HTTP/2, no keepalive, no shared limits. |
| 4 | Quorum & incident detection | **F** | 87% correctness; both missed and duplicate incidents; duplicates permanently brick the dependency via `scalar_one_or_none()`. |
| 5 | Data integrity (observations) | **F** | Best-effort dual write, failures swallowed at `WARNING`; 89% observation loss on affected deps; evidence signs incomplete data. |
| 6 | Partitioning strategy | **D** | Declared but unmanaged; single DEFAULT partition; rows in DEFAULT block future `ATTACH`. |
| 7 | Worker design | **C** | APScheduler in-process is a reasonable simplification, but it shares the API event loop — probe latency directly steals API CPU, and it cannot scale past one replica without duplicate execution. |
| 8 | Security | **B−** | RBAC, tenancy, key revocation, webhook HMAC all correct. Loses points for the idempotency leak (P0), SHA-256 keys, and no create-time SSRF. |
| 9 | Observability | **F** | No `/metrics`, no tracing, no structured logs; `/health` hits the DB on every call. Flying blind. |
| 10 | Operational excellence | **D** | Migrations in the start command; compose file references a Celery stack the app no longer runs; no `/health/live` vs `/health/ready`. |

---

## Remediation Roadmap

### P0 — Fix This Week

---

#### P0-1 · Quorum race brick — the highest-severity defect

**Files:** `app/modules/incidents/repository.py:41-49`, `app/modules/incidents/service.py:100-113`
**Impact:** silent monitoring outage per affected endpoint + unresolvable incidents.

Two mutually reinforcing bugs: `scalar_one_or_none()` throws once duplicates exist, and nothing prevents duplicates. Fix both — make the read tolerant *and* make duplicates impossible.

**Step 1 — migration (make duplicates structurally impossible):**

```python
# app/db/migrations/versions/0012_incident_quorum_integrity.py
def upgrade() -> None:
    # Collapse any existing duplicates, keeping the earliest per dependency.
    op.execute("""
        UPDATE incidents i SET status='resolved',
               resolved_at=COALESCE(i.resolved_at, now())
        WHERE i.status='open' AND i.id <> (
            SELECT id FROM incidents j
            WHERE j.dependency_id=i.dependency_id AND j.status='open'
            ORDER BY j.started_at ASC, j.id ASC LIMIT 1)
    """)
    op.execute("""
        CREATE UNIQUE INDEX CONCURRENTLY ix_incidents_one_open_per_dep
        ON incidents (dependency_id) WHERE status = 'open'
    """)
```

**Step 2 — tolerant read + atomic create:**

```diff
--- a/app/modules/incidents/repository.py
+++ b/app/modules/incidents/repository.py
@@
     async def get_open_for_dependency(
-        session: AsyncSession, dependency_id: uuid.UUID
+        session: AsyncSession, dependency_id: uuid.UUID, *, for_update: bool = False
     ) -> Incident | None:
         query = select(Incident).where(
             Incident.dependency_id == dependency_id,
             Incident.status == IncidentStatus.OPEN.value,
-        )
+        ).order_by(Incident.started_at.asc()).limit(1)
+        if for_update:
+            query = query.with_for_update(skip_locked=False)
         result = await session.execute(query)
-        return result.scalar_one_or_none()
+        # NEVER scalar_one_or_none(): legacy duplicates must not brick checks.
+        return result.scalars().first()
```

```diff
--- a/app/modules/incidents/service.py
+++ b/app/modules/incidents/service.py
@@ async def check_and_create_incident(
-        existing = await self.repository.get_open_for_dependency(
-            session, dependency_id
-        )
-        if existing:
-            return existing
-
-        incident = await self.repository.create(...)
+        # Serialise concurrent regions on the dependency row itself.
+        await session.execute(
+            select(Dependency.id).where(Dependency.id == dependency_id)
+            .with_for_update()
+        )
+        existing = await self.repository.get_open_for_dependency(
+            session, dependency_id, for_update=True
+        )
+        if existing:
+            return existing
+        try:
+            async with session.begin_nested():
+                incident = await self.repository.create(...)
+        except IntegrityError:
+            # Lost the race to a peer region — adopt their incident.
+            return await self.repository.get_open_for_dependency(
+                session, dependency_id)
```

**Expected impact:** incident correctness 87% → 100%; permanent bricking eliminated.

**Validating test:**

```python
@pytest.mark.asyncio
async def test_concurrent_regions_create_exactly_one_incident(dep_id, sessionmaker):
    async def probe(region):
        async with sessionmaker() as s:
            await check_service.execute_check(s, dep_id, region); await s.commit()
    for _ in range(20):
        await asyncio.gather(probe("us-east"), probe("eu-west"))
    assert await count_open_incidents(dep_id) == 1

@pytest.mark.asyncio
async def test_preexisting_duplicates_do_not_brick_checks(dep_id, sessionmaker):
    await seed_duplicate_open_incidents(dep_id, n=2)
    async with sessionmaker() as s:
        assert await check_service.execute_check(s, dep_id, "us-east") is not None
```

---

#### P0-2 · Cross-tenant idempotency replay

**File:** `app/main.py:73-118` · **Impact:** confirmed tenant data disclosure.

```diff
--- a/app/main.py
+++ b/app/main.py
@@ class IdempotencyMiddleware(BaseHTTPMiddleware):
-        idempotency_key = request.headers.get("idempotency-key")
-        if not idempotency_key or request.method not in ["POST", "PATCH"]:
-            return await call_next(request)
-        try:
-            cache_key = f"idempotency:{idempotency_key}"
-            cached_resp = await safe_redis_get(cache_key)
+        idempotency_key = request.headers.get("idempotency-key")
+        if not idempotency_key or request.method not in ["POST", "PATCH"]:
+            return await call_next(request)
+        # Bind the cache entry to the CALLER and the exact target, so one
+        # tenant can never replay another tenant's key, and so the same key
+        # on a different route cannot return an unrelated body.
+        principal = _principal_fingerprint(request)   # sub/jti from JWT or API-key hash
+        scope = hashlib.sha256(
+            f"{principal}|{request.method}|{request.url.path}|"
+            f"{hashlib.sha256(await request.body()).hexdigest()}".encode()
+        ).hexdigest()
+        cache_key = f"idempotency:{scope}:{idempotency_key}"
+        try:
+            cached_resp = await safe_redis_get(cache_key)
             if cached_resp:
                 ...
-            response = await call_next(request)
+            # Single-flight: only the first concurrent caller executes.
+            if not await safe_redis_setnx(f"{cache_key}:lock", "1", ttl=60):
+                return Response(status_code=409, media_type="application/json",
+                                content='{"error":{"code":"IDEMPOTENT_REQUEST_IN_FLIGHT"}}')
+            response = await call_next(request)
```

**Expected impact:** eliminates the leak; 200 concurrent same-key POSTs → exactly 1 row.

**Validating test:**

```python
def test_idempotency_is_tenant_scoped(user_a, user_b):
    key = str(uuid.uuid4())
    a = post("/v1/orgs", json={"name": "A"}, token=user_a, idem=key)
    b = post("/v1/orgs", json={"name": "B"}, token=user_b, idem=key)
    assert b.json()["id"] != a.json()["id"]     # no cross-tenant echo

def test_idempotency_single_flight():
    key = str(uuid.uuid4())
    rs = run_concurrently(200, lambda: post("/v1/orgs", json={"name":"X"}, idem=key))
    assert len({r.json()["id"] for r in rs if r.status_code == 201}) == 1
```

---

#### P0-3 · Observation loss corrupts the evidence chain

**File:** `app/modules/checks/service.py:29-84` (write), `:254` (call site)
**Impact:** SHA-256-signed evidence attests to incomplete outage data.

Two changes: record the observation **before** incident evaluation, and make loss loud and recoverable via an outbox rather than a swallowed `WARNING`.

```diff
--- a/app/modules/checks/service.py
+++ b/app/modules/checks/service.py
@@ async def execute_check(...):
         result = await self.repository.create(...)
+        # Observations are the evidentiary source of truth: persist BEFORE the
+        # incident logic, which is the code path that actually raises.
+        await self._record_observation(session, result, url, method)
@@
-        # Evaluate Quorum Logic
+        # Evaluate Quorum Logic
         recent_results = await self.repository.list_recent_for_dependency(...)
@@
-        await self._record_observation(session, result, url, method)
         return result
```

```diff
@@ async def _record_observation(...):
         except Exception as exc:
-            logger.warning(
-                "Failed to record observation for dependency %s: %s",
-                result.dependency_id, exc)
+            # Never silently drop evidentiary data. Queue for replay and
+            # emit a metric an on-call engineer can alert on.
+            OBSERVATION_WRITE_FAILURES.labels(
+                org_id=str(result.org_id)).inc()
+            await session.execute(insert(ObservationOutbox).values(
+                check_result_id=result.id, payload=dto.model_dump(mode="json"),
+                created_at=datetime.now(timezone.utc)))
+            logger.error(
+                "Observation write failed for dependency %s — queued to outbox",
+                result.dependency_id, exc_info=exc)
```

Additionally, evidence generation must refuse to sign a window it knows is incomplete:

```diff
--- a/app/modules/evidence/service.py
+++ b/app/modules/evidence/service.py
@@ observations = await ObservationRepository.list_for_source(...)
+    expected = await CheckRepository.count_between(
+        session, incident.dependency_id, window_start, window_end)
+    if len(observations) < expected:
+        raise EvidenceIntegrityError(
+            f"Refusing to sign incomplete evidence: {len(observations)} "
+            f"observations for {expected} checks in window")
```

**Expected impact:** observation loss 2% global / 89% on affected deps → 0%; no report can ever be signed over a known-incomplete window.

**Validating test:**

```python
@pytest.mark.asyncio
async def test_observation_written_even_when_incident_logic_fails(monkeypatch, dep):
    monkeypatch.setattr(incident_service, "check_and_create_incident",
                        AsyncMock(side_effect=RuntimeError("boom")))
    async with sessionmaker() as s:
        await check_service.execute_check(s, dep.id, "us-east"); await s.commit()
    assert await count_check_results(dep.id) == await count_observations(dep.id)

@pytest.mark.asyncio
async def test_evidence_refuses_incomplete_window(incident):
    await delete_one_observation_in_window(incident)
    with pytest.raises(EvidenceIntegrityError):
        await evidence_service.generate_for_incident(session, incident.id)
```

---

### P1 — Fix This Month

---

#### P1-1 · Scheduler: fan out, bound concurrency, honour intervals

**File:** `app/infrastructure/scheduler.py:36-52`, `app/modules/checks/service.py:102-121`, `app/modules/dependencies/repository.py:59-69`

```diff
--- a/app/modules/dependencies/repository.py
+++ b/app/modules/dependencies/repository.py
@@ async def get_due_dependencies(session):
         query = select(Dependency).where(
             Dependency.is_active == True, Dependency.is_deleted == False,
             Dependency.next_check_at <= now,
-        )
+        ).order_by(Dependency.next_check_at.asc()).limit(500) \
+         .with_for_update(skip_locked=True)   # safe with >1 replica
```

```diff
--- a/app/modules/checks/service.py
+++ b/app/modules/checks/service.py
@@ async def schedule_due_checks(self, session):
-        for dep in due_deps:
-            ...
-            for reg in regions:
-                await self.execute_check(session, dep.id, reg)   # serial, shared session
+        # Claim the batch in a SHORT transaction, then release the session.
+        claims = [(d.id, r) for d in due_deps for r in (d.regions or DEFAULT_REGIONS)]
+        for dep in due_deps:
+            dep.next_check_at = now + timedelta(seconds=dep.check_interval_seconds)
+        await session.commit()
+
+        sem = asyncio.Semaphore(settings.CHECK_CONCURRENCY)   # default 50
+        async def run(dep_id, region):
+            async with sem:                                    # bounded fan-out
+                async with get_session_maker()() as s:         # session per check
+                    try:
+                        await self.execute_check(s, dep_id, region); await s.commit()
+                    except Exception:
+                        await s.rollback()
+                        logger.exception("check failed dep=%s region=%s", dep_id, region)
+        await asyncio.gather(*(run(d, r) for d, r in claims))
```

Run the beat at **5s** so sub-30s intervals are actually honoured:

```diff
-        trigger=IntervalTrigger(seconds=30),
+        trigger=IntervalTrigger(seconds=5),
+        coalesce=True, max_instances=1,
```

**Expected impact:** 50-dep cycle 35.1s → **<3s**; throughput 30% → ~100%; 5s/15s tiers delivered as sold.
**Test:** `test_50_deps_complete_within_one_beat` — assert `count(check_results) >= 95%` of nominal after 60s, and assert cycle wall-time < beat interval.

> ⚠️ **Sequencing:** ship P1-2 *in the same release*. Raising concurrency without raising the pool converts scenario A into scenario B.

#### P1-2 · Connection pool sizing

**File:** `app/db/session.py:143-146`

```diff
-                pool_size=10,
-                max_overflow=20,
-                pool_timeout=30,
+                pool_size=settings.DB_POOL_SIZE,        # 20
+                max_overflow=settings.DB_MAX_OVERFLOW,  # 40
+                pool_timeout=10,       # fail fast; don't queue 30s behind a stampede
+                pool_recycle=1800,     # avoid stale conns behind PgBouncer/NAT
```

Keep `pool_size + max_overflow` per replica × replicas < PG `max_connections`. **Test:** `test_pool_rejects_fast_under_stampede` — 200 concurrent max-range queries, assert p99 < 10s and zero 30s hangs.

#### P1-3 · Shared HTTP client with keepalive + HTTP/2

**File:** `app/modules/checks/service.py:177`

```diff
+_CLIENT: httpx.AsyncClient | None = None
+def get_probe_client() -> httpx.AsyncClient:
+    global _CLIENT
+    if _CLIENT is None:
+        _CLIENT = httpx.AsyncClient(
+            http2=True,
+            limits=httpx.Limits(max_connections=200,
+                                max_keepalive_connections=100,
+                                keepalive_expiry=90.0),
+            follow_redirects=False,   # explicit: redirects are a signal, not success
+        )
+    return _CLIENT
@@
-            async with httpx.AsyncClient(timeout=timeout, verify=True) as client:
-                response = await client.request(method=method, url=url, headers=headers)
+            client = get_probe_client()
+            response = await client.request(
+                method=method, url=url, headers=headers, timeout=timeout)
```

Close it in the lifespan shutdown. **Expected impact:** removes 15–31% handshake inflation from reported `latency_ms`; eliminates socket churn.
**Test:** `test_probe_reuses_connection` — assert the same `id(transport.pool)` and that the 2nd probe to one host is measurably faster.

#### P1-4 · Partition management

**File:** new migration + monthly job. Because rows already sit in `check_results_default`, ATTACH will fail until they are drained.

```python
def upgrade() -> None:
    for i in range(-1, 13):                       # last month .. next 12
        start, end = month_bounds(i)
        op.execute(f"""CREATE TABLE IF NOT EXISTS check_results_{start:%Y_%m}
            PARTITION OF check_results FOR VALUES FROM ('{start}') TO ('{end}')""")
    op.execute("""INSERT INTO check_results SELECT * FROM check_results_default
                  ON CONFLICT DO NOTHING""")      # drain, then prune DEFAULT
    op.execute("DELETE FROM check_results_default")
```

Add an APScheduler job that pre-creates N+3 months and detaches/drops beyond retention. **Test:** `test_insert_next_month_lands_in_named_partition` — assert `tableoid::regclass != 'check_results_default'`.

#### P1-5 · Create-time SSRF validation & redirect semantics

**Files:** `app/modules/dependencies/service.py:68`, `app/modules/checks/service.py:177`

```diff
+        # Validate at CREATE time, not only at probe time, so tenants get an
+        # immediate 422 instead of a dependency that silently never succeeds.
+        ok, reason = is_url_safe(payload.endpoint_url)
+        if not ok:
+            raise ValidationException(f"endpoint_url rejected: {reason}")
```

Redirects: with `follow_redirects=False` (P1-3), a 301/302 is recorded as `is_up=False` unless the tenant lists it in `expected_status_codes` — make that explicit in the API docs, and add a per-dependency `follow_redirects: bool = False` field. **Test:** `test_create_rejects_private_url` (422) and `test_redirect_recorded_as_configured`.

#### P1-6 · Paginate public vendor list

**File:** `app/modules/vendors/router.py` — `GET /v1/public/vendors` returns an unbounded array on an unauthenticated endpoint.

```diff
-async def list_vendors(...) -> list[VendorResponse]:
+async def list_vendors(page: int = Query(1, ge=1),
+                       size: int = Query(50, ge=1, le=200)) -> Page[VendorResponse]:
```

**Test:** `test_public_vendors_paginated` — seed 500, assert `len(items) == 50` and `total == 500`.

---

### P2 — Fix This Quarter

#### P2-1 · Observability (currently grade F)

Add `prometheus-fastapi-instrumentator` + OpenTelemetry, and the counters that would have caught every P0 in this report:

```python
CHECKS_EXECUTED       = Counter("reliastra_checks_total", ["region", "result"])
SCHEDULER_CYCLE       = Histogram("reliastra_scheduler_cycle_seconds")
OBSERVATION_FAILURES  = Counter("reliastra_observation_write_failures_total", ["org_id"])
INCIDENT_RACE_LOST    = Counter("reliastra_incident_create_conflicts_total")
DUPLICATE_OPEN_INCIDENTS = Gauge("reliastra_duplicate_open_incidents")
```

Alert on `observation_write_failures_total > 0` and `duplicate_open_incidents > 0` — both should be flatline zero.
**Test:** `test_metrics_endpoint_exposes_check_counter`.

#### P2-2 · Split liveness from readiness

**File:** `app/main.py:190-225` — `/health` runs `SELECT 1` on every call; a load balancer polling it adds DB load exactly when the DB is the thing struggling.

```python
@app.get("/health/live")   # no I/O — is the process alive?
async def live(): return {"status": "ok"}

@app.get("/health/ready")  # cached 5s — should we receive traffic?
async def ready(response: Response): ...   # existing DB+Redis logic, memoised
```

**Test:** `test_liveness_ok_when_db_down`.

#### P2-3 · Webhook replay protection

`app/modules/billing/service.py:329-345` verifies HMAC but not freshness. Persist `event.id` with a unique constraint and reject events older than 5 minutes. **Test:** `test_replayed_webhook_rejected_second_time`.

#### P2-4 · `/v1/verify/{id}` should 404 on unknown IDs

`app/modules/verification/router.py:24-26` returns HTTP 200 with `found:false` — a verifier checking status codes reads that as valid. Return 404, and stop masking DB outages as "not found" (`service_degraded` should be a 503). **Test:** `test_verify_unknown_returns_404`.

#### P2-5 · Expose `role` on `GET /v1/orgs`

Test #10: the org list omits the caller's role, forcing clients to guess. Add `role` to the response model. **Test:** `test_org_list_includes_caller_role`.

---

### P3 — Strategic (10x scale)

1. **Redis ZSET scheduler.** Replace due-scanning with `ZADD reliastra:due <next_ts> <dep_id:region>` + `ZRANGEBYSCORE`. Moves scheduling off the DB entirely and makes multi-replica dispatch atomic via `ZPOPMIN`. Keeps the monolith; changes only the claim mechanism.
2. **Per-dependency circuit breaker.** After N consecutive failures, back off exponentially (10s → 5m). A vendor with a 60s timeout currently burns a probe slot every cycle forever.
3. **Split the scheduler from the API process.** Same codebase, same image, different entrypoint (`--mode scheduler`). Today probe latency competes with API request handling on one event loop. This is not microservices — it is one deployable run in two roles.
4. **Observations as the sole source of truth.** Once P0-3 lands and divergence is zero, retire the `check_results` dual write and make `check_results` a view over observations. Removes the entire class of dual-write bugs.
5. **TimescaleDB or `pg_partman`.** Once partitioning is real (P1-4), hypertables give automatic chunking, compression (~10x on this workload) and continuous aggregates that would make the dashboard queries O(1).

---

## Priority Summary

| Order | Item | Dimension | Effort |
|---|---|---|---|
| 1 | P0-1 Quorum race brick | Data integrity | M |
| 2 | P0-3 Observation loss / evidence corruption | Data integrity | M |
| 3 | P0-2 Cross-tenant idempotency leak | Security | S |
| 4 | P1-1 + P1-2 Scheduler fan-out **and** pool (ship together) | Scalability | L |
| 5 | P1-3 Shared HTTP client | Scalability / cost | S |
| 6 | P1-4 Partition management | Scalability / cost | M |
| 7 | P1-5/6 SSRF at create, redirects, pagination | Security / correctness | S |
| 8 | P2-* Observability, health split, replay, verify 404 | Operability | M |

---

## Appendix: Test Scripts

All scripts are committed under `audit/` and are re-runnable against a live stack:

| Script | Purpose |
|---|---|
| `audit/functional_suite.py` | 67 assertions across the full API surface (Step 2) |
| `audit/stress_suite.py` | Scenarios A–H with measured thresholds (Step 3) |
| `audit/quorum_trials.py` | 15-trial statistical characterisation of the quorum race |
| `audit/prove_poisoning.py` | Demonstrates the permanent-brick failure mode |
| `audit/out/*.json` | Raw machine-readable results |

**Reproduce:**

```bash
export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 &
.venv/bin/python audit/functional_suite.py
.venv/bin/python audit/stress_suite.py
.venv/bin/python audit/quorum_trials.py
```

**Regression suite status after the three fixes applied during this audit:** `73 passed, 6 failed` (previously **0 runnable**, 79 collection errors). The 6 remaining failures are pre-existing and unrelated to the fixes: a founding-customer plan-interval assertion (`assert 15 == 60`), two `UserResponse` MagicMock validation failures, a `_patch_object` signature error, and two API assertions (`assert 3 == 5`, `404 == 200`).
