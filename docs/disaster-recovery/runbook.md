# Disaster recovery runbook

For each scenario: **detection → mitigation → recovery → verification**.

## 1. API server dies

- Detection: `/health/live` fails; load balancer marks instance down.
- Mitigation: LB routes to other stateless API instances; no state is lost.
- Recovery: restart/roll a new instance (same config).
- Verification: `/health/ready` passes; authenticated request succeeds.

## 2. Worker dies

- Detection: `workers.heartbeat_at` stale; `worker_active_jobs` drops;
  leases accumulate (`check_jobs` stuck in `leased`).
- Mitigation: none needed — the scheduler's reclaim loop re-queues jobs
  after `lease_until` with backoff; other workers pick them up.
- Recovery: restart the worker (or let the fleet absorb the load).
- Verification: expired leases transition to `pending`/`succeeded`;
  `jobs_expired_total` and `jobs_requeued_total` metrics reflect it.

## 3. Scheduler dies

- Detection: `jobs_created_total` flatlines; `monitors.next_run_at` drifts
  past due.
- Mitigation: existing jobs still execute; missed runs are handled by the
  missed-job window on restart (backlog dropped, not burst).
- Recovery: restart scheduler (or another replica takes over).
- Verification: new jobs appear; next_run_at advances.

## 4. Redis dies

- Detection: `redis_operations_total{result="error"}`; rate limiter logs.
- Mitigation: the limiter falls back to in-memory (single-process accuracy);
  nothing else depends on Redis for correctness.
- Recovery: restart Redis or restore from AOF/RDB.
- Verification: rate limits apply again across instances.

## 5. PostgreSQL unavailable

- Detection: `/health/ready` fails; `database_query_duration` errors;
  API returns 503.
- Mitigation: API stops serving (readiness), workers hold leases until
  expiry then retry; **no state corruption**: in-flight transactions abort
  cleanly.
- Recovery: restore from backup per backup-restore.md, or wait out the
  outage; enable WAL archiving for PITR.
- Verification: migrations status, sample queries, evidence verification.

## 6. Object storage unavailable

- Detection: evidence generation failures (`evidence_generation_failures_total`);
  verification returns artifact errors.
- Mitigation: generation retries via the outbox (backoff); incident and
  evidence metadata remain intact in PostgreSQL.
- Recovery: restore the bucket (versioning) or point config at a replica.
- Verification: `GET /v1/evidence/{id}/verify` passes; hash matches.

## 7. Entire region dies

- Detection: cross-region health checks fail; replication lag alerts.
- Mitigation: fail over DNS/LB to another region (API + workers are
  region-agnostic; observation regions are data).
- Recovery: promote the replica or restore from the offsite backup + WAL;
  re-point configs.
- Verification: end-to-end check runs, incident + evidence accessible.

## 8. Credential compromise

- Detection: suspicious audit logs, failed-login spikes, API key abuse.
- Mitigation: revoke affected sessions (`sessions`), revoke API keys
  (`api_keys` status='revoked'), rotate the encryption master key (new
  version; old data stays readable with the recorded key version).
- Recovery: rotate passwords; re-issue API keys; review audit logs.
- Verification: old tokens/keys rejected; new credentials work.

## 9. Corrupted deployment

- Detection: startup validation failure (config validation fails fast),
  readiness failing, panic storms.
- Mitigation: roll back the binary; keep previous version compatible via
  additive migrations.
- Recovery: redeploy previous release; `migrate status` must match.
- Verification: health + smoke tests.

## 10. Accidental database deletion

- Detection: `DROP`/deletion alerts, missing tables, `pg_stat` anomalies.
- Mitigation: stop writes immediately; snapshot what remains.
- Recovery: restore the latest backup (logical + WAL to last good point);
  restore object store via versioning if needed.
- Verification: full backup verification procedure (record counts +
  evidence hashes + integration tests).
