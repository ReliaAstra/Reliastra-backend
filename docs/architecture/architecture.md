# Reliastra Phase 1 — Architecture

## 1. Components and responsibilities

Reliastra is a **modular monolith with separate worker processes**:
one codebase, one database, several deployable runtime processes.

| Process | Responsibility | Scale |
|---|---|---|
| `api` | Authentication, authorization, CRUD, queries, API keys, evidence requests. **Never executes checks synchronously.** | Stateless; scale horizontally behind a load balancer |
| `scheduler` | Determines which monitors are due, creates durable `check_jobs`. Never executes checks. | Multiple schedulers may run concurrently (idempotent job creation) |
| `worker` | Leases and executes check jobs, writes results + normalized observations. | Horizontally scalable; org-fair concurrency |
| `notifier` | Drains the transactional outbox: fan-out to notification channels, triggers async evidence generation. | Horizontally scalable |
| `migrate` | Applies embedded SQL migrations deterministically. | Run once per deploy, before new code |

The domain layer is organized into packages with strict dependency
direction: `pkg/*` (no internal deps) ← `internal/platform/*` (infra) ←
`internal/{auth,organizations,...,evidence}` (domain) ← `internal/api`
(HTTP adapters) ← `cmd/*` (composition roots). **Business logic never lives
in HTTP handlers**; handlers are thin adapters over services.

## 2. Data flow

```
API (CRUD) ──► PostgreSQL (source of truth)
                  ▲
Scheduler ──► creates check_jobs (idempotent, unique monitor+region+scheduled_for)
                  │
                  ▼
Worker ──► leases job (FOR UPDATE SKIP LOCKED) ──► executes HTTP check (SSRF-safe,
          timeout-bound) ──► transaction: check_result + observation
          + job status + outbox event ──COMMIT──► incident detector (idempotent)
                  │
                  ▼
Incident detector ──► candidate/confirmed/resolved incidents + outbox events
                  │
                  ▼
Correlation engine (deterministic v1) ──► incident_correlations rows
                  │
                  ▼
Notifier ──► evidence generation (canonical JSON + PDF ──► object storage,
            hash in PostgreSQL) ──► email/Slack deliveries (idempotent,
            retry, dead-letter)
```

Key invariants:

- **Result, observation, job status and outbox event commit atomically** — a
  crash cannot lose a completed check or its notification trigger.
- **Incidents are re-derivable from durable observations.** Detection is
  idempotent; a unique partial index guarantees one open incident per target.
- **Evidence is byte-immutable.** The canonical artifact in object storage is
  hashed (SHA-256); the hash, algorithm, version and timestamps live in
  PostgreSQL. Verification re-reads and re-hashes.

## 3. Failure boundaries

| Component failure | Effect | Recovery |
|---|---|---|
| API dies | New requests fail; nothing else is affected | Load balancer reroutes; stateless restart |
| Scheduler dies | No new jobs until it returns | Jobs already created still execute; restart scheduler |
| Worker dies mid-check | Leased jobs expire (`lease_until`) | Scheduler reclaim loop re-queues with backoff |
| Notifier dies | Outbox events stay `pending` | Restart; events processed in order |
| Redis disappears | Rate limiting degrades to in-memory; coordination unaffected | Redis optional; PostgreSQL remains authoritative |
| PostgreSQL slow/down | Readiness flips; API returns 503s; workers hold leases until expiry | Backpressure + lease expiry; no state corruption |
| Object storage unavailable | Evidence generation retries via outbox; verification reports unavailable | Restart or restore storage; records keep hash for later verification |
| External target times out | Check fails with normalized `connection_timeout`; job retries with backoff | Automatic |
| Notification provider fails | Delivery retries with backoff → dead-letter; incident transaction already committed | Ops tooling re-queues dead letters |

## 4. Scaling strategy

- **API**: stateless, scale N. Sessions/keys are in PostgreSQL; rate limits use
  Redis when available.
- **Workers**: scale N; each leases jobs with `FOR UPDATE SKIP LOCKED` so two
  workers never execute the same job. Per-organization concurrency gate
  (org fairness) prevents one tenant from starving others.
- **Scheduler**: scale N; job creation is idempotent and `next_run_at`
  advancement is conditional, so concurrent schedulers cannot double-create.
- **Database**: indexes target the actual query patterns (due-monitor scan,
  lease pickup, monitor history, incident lookups). `check_results` and
  `observations` are designed for time-based partitioning (see
  [database.md](database.md)).
- **Object storage**: evidence blobs are content-addressed by key + hash;
  versioning/lifecycle handled by the storage backend.

## 5. Consistency model

**Strong consistency (PostgreSQL):** organization ownership, monitor
configuration, incident state transitions, evidence finalization, API key
revocation, job leasing.

**Eventual consistency (acceptable):** dashboards, aggregate metrics, public
charts, notification delivery, analytics.

## 6. Multi-region observation

Regions are **data-driven** (`regions` table). A monitor is assigned one or
more regions (`monitor_regions`); the scheduler creates one job per
(monitor, region, scheduled time). Workers declare `region_id` and heartbeat
into `workers`. Adding `africa-west` is configuration + seed data, never a
code change.

## 7. The core invariant

> **Observation is disposable. Evidence is durable.**

Raw check results are bounded and short-retention. Incidents summarize.
Caches, Redis, workers and processes can disappear. Finalized evidence and
the observation data required to explain an incident are retained long-term,
hashed, and verifiable.
