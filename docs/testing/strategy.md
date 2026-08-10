# Testing strategy

## Unit tests

- Domain logic: incidents state machine (allowed/rejected transitions),
  correlation scoring factors, scheduling jitter/advance, retry backoff
  bounds, quota enforcement, auth token hashing, password verification.
- Security: SSRF guard (blocked CIDRs, DNS-rebinding simulation via injected
  resolver, redirect validation), secret redaction, IDOR (cross-tenant
  queries must fail), scope enforcement.
- Invariants: finalized evidence bytes never change; resolved incidents
  cannot go back to candidate; duplicate jobs do not create duplicate
  incidents; retries do not create duplicate notifications.

## Integration tests (tests/integration)

Run against a **real PostgreSQL** (PGlite wire server in the sandbox, or any
PostgreSQL via `RELI_TEST_DATABASE_URL`) + real object store (filesystem
backend). They exercise:

- migrations up/down/status
- the full e2e flow: register → org → project → service → dependency →
  link → monitor → scheduler creates jobs → worker executes against a local
  flaky HTTP target → observations → incident candidate/confirmed →
  target recovers → incident resolved → correlation persisted → notifier
  generates evidence → evidence finalized → verify → download JSON+PDF

## API tests

All major endpoints via the real HTTP router (in-process httptest):
auth, organizations, projects, services, dependencies, links, monitors,
results, incidents, evidence, API keys, channels, audit, public vendors.

## Security tests

- IDOR: Org A attempts to read Org B's project/service/monitor/incident →
  403/404.
- SSRF: monitors targeting `http://127.0.0.1`, `http://169.254.169.254`,
  decimal-IP forms, redirects to private IPs → `ssrf_blocked`.
- Authentication bypass: missing/expired/revoked tokens rejected.
- Authorization bypass: viewer creating monitors → 403; API key without
  scope → 403.
- Rate limits: burst past limit → 429.
- Secret exposure: monitor config responses never contain the plaintext
  secret; DB `monitor_secrets` contains ciphertext only.

## Failure tests

- Kill worker mid-check → lease expires → job re-queued → completes.
- Restart scheduler → no duplicate jobs.
- Duplicate job delivery (insert same monitor+region+time twice) → one row.
- Notification provider returns 500 → delivery retries with backoff → dead
  letter; incident transaction unaffected.
- Object storage unavailable → evidence generation fails visibly, outbox
  retries, no partial state.

## Load tests (tests/load)

- API: 100–500 concurrent clients on CRUD + queries; measure throughput,
  latency, DB utilization.
- Scheduler: 10,000 due monitors; verify job creation rate and no duplicate
  jobs.
- Workers: large batches of simultaneous checks against a local target;
  measure queue delay, worker utilization, failed jobs.

Run with `go test -tags load ./tests/load/...` and capture the metrics
before/after.

## Chaos / failure tests (tests/chaos)

Basic simulations: kill worker during check; restart scheduler; stop Redis;
pause PostgreSQL (stop the wire server); return 500 from notification
provider. Verify the system recovers without corrupting durable state
(observations/incidents/evidence unchanged or repaired).
