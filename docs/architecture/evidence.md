# Evidence specification

## Canonical structure

A finalized evidence artifact is a single JSON document (schema `1.0`),
generated deterministically from durable state. Field order is fixed by the
Go struct, so the stored bytes equal the hashed bytes.

```
{
  schema_version, evidence_id, version,
  methodology_version, correlation_algorithm_version, scoring_config_version,
  generated_at,
  incident:        {id, number, status, severity, title, summary,
                    started_at, detected_at, resolved_at?},
  project:         {id, name},
  service?:        {id, name},
  dependency?:     {id, name},
  attribution?:    {dependency_id, dependency_name, confidence,
                    evidence_score, factors{...}, explanations[]},
  timeline:        [{at, event, detail?}...],
  measurements:    {availability{service, dependency}, avg_latency_ms{...},
                    status_codes{}, error_classes{}, total_observations},
  regions:         [{region_id, region_name, observations, failed, availability}...],
  observation_ids: [...],          // raw evidence references
  monitor_snapshots: [{monitor_id, name, type, target, interval_seconds,
                       timeout_seconds, configuration_sha}...],
  integrity:       {hash_algorithm: "sha256"}
}
```

## Hashing and immutability

1. The package is assembled from durable rows (incident, correlations,
   observations, monitor snapshots).
2. `CanonicalBytes` marshals it (UTC RFC3339 timestamps, fixed field order).
3. `HashPackage` computes `SHA-256(canonical bytes)`.
4. The canonical bytes are stored in object storage under
   `evidence/<incident_id>/<NNN>.json` (and a `.pdf` sibling); the hash,
   algorithm (`sha256`), version, methodology and timestamps are recorded in
   `evidence_records`.

**The authoritative hash lives in PostgreSQL.** Verification re-reads the
artifact, re-computes SHA-256, and compares. The artifact's `integrity`
section declares the algorithm (a self-referential embedded hash would make
the digest unstable).

**Immutability rules:**

- Finalized records are never updated in place.
- A re-generation creates a new version (`UNIQUE (incident_id, version)`).
- `evidence_records` has no update path for finalized rows in the API; the
  `generating → finalized/failed` transition is the only mutation, enforced
  by the store (`WHERE status='generating'`).
- `GET /v1/evidence/{id}/verify` checks: status finalized, artifact exists,
  artifact readable, SHA-256 matches, algorithm is sha256.

## Reproducibility metadata

Each artifact embeds: `correlation_algorithm_version`,
`scoring_config_version`, `methodology_version`, monitor configuration
snapshots (hashed, secrets excluded), region configuration snapshots,
observation ids, and `generated_at`. Historical evidence remains
interpretable after configuration changes.

## Storage

- JSON + PDF in S3-compatible object storage (filesystem backend in dev).
- PostgreSQL stores only metadata: hash, algorithm, version, storage key,
  size, status. **Large blobs never live in PostgreSQL.**
- Buckets should enable versioning + lifecycle policy (see
  backup-restore.md).

## PDF report

Generated from the same canonical package (async, never part of an incident
transaction). Contents: header band, incident identity, likely dependency,
confidence, evidence score, timeline, correlation explanations, measurements
table, regions table, integrity footer.
