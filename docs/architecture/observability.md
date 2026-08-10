# Observability

## Structured logs

All processes emit JSON logs via `log/slog` with:

```
{"time":"...","level":"INFO","service":"api","request_id":"...",
 "trace_id":"...","span_id":"...","organization_id":"...","actor_id":"...",
 "component":"...","msg":"...","error":"...", ...}
```

- Request-scoped fields propagate through the context (`logging.WithContext`).
- **Secrets are never logged**: `logging.Redact`/`RedactMap` mark sensitive
  fields; monitor credentials are decrypted only inside the executor and
  never passed to loggers.

## Metrics (Prometheus, /metrics)

Process-level registry (each binary exposes its own; scrape all):

- API: `api_requests_total{method,path,status}`,
  `api_request_duration_seconds{method,path}`
- Jobs: `jobs_created_total{monitor_type}`, `jobs_completed_total{status}`,
  `jobs_failed_total`, `jobs_retried_total`, `jobs_expired_total`,
  `jobs_requeued_total`, `job_lease_wait_seconds`
- Workers: `worker_active_jobs`, `worker_capacity`
- Checks: `check_success_total{monitor_type,region}`,
  `check_failure_total{monitor_type,region,failure_class}`
- Incidents: `incident_created_total`, `incident_confirmed_total`,
  `incident_resolved_total`, `incident_false_positive_total`
- Correlation: `correlation_runs_total`
- Evidence: `evidence_generated_total`, `evidence_generation_failures_total`
- Notifications: `notification_sent_total{channel_type}`,
  `notification_failed_total{channel_type}`
- Database: `database_pool_connections`, `database_query_duration_seconds{op}`
- Redis: `redis_operations_total{result}`
- Outbox: `outbox_events_processed_total{event_type,result}`

## Health endpoints

- `GET /health/live` — process liveness only. **Never depends on
  PostgreSQL** (an orchestrator must not restart a process just because a
  dependency is down).
- `GET /health/ready` — probes PostgreSQL, Redis (if configured), object
  storage; 503 when any required dependency is unavailable.

## Tracing

Phase 1 ships a no-op/log tracer (`pkg/tracing`) with real trace/span ids so
logs correlate by `trace_id`. The `Tracer` interface is the OpenTelemetry
seam: to export, swap `tracing.Global` for an OTel-backed implementation
(start a `TracerProvider` in `cmd/*`, keep the same `Start/End` call sites).
Trace context must never carry secrets; redact attributes at span creation.
