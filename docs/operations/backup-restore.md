# Backup and restore plan

## Objectives

- **RPO (Recovery Point Objective):** ≤ 15 minutes of data loss in normal
  operations (logical daily backup + continuous WAL archiving); the daily
  logical backup alone gives an RPO of 24 h if WAL archiving is unavailable.
- **RTO (Recovery Time Objective):** ≤ 60 minutes to serve reads/writes
  again from backups on a replacement instance; ≤ 4 hours for a full
  restore + verification of a large database.

## PostgreSQL backups

### Logical backup (daily)

```
pg_dump -Fc --no-owner --no-privileges -d "$DATABASE_URL" \
  > "reliastra-$(date +%F).dump"
```

- Custom-format (`-Fc`) for compressed, selective restore.
- Retained **14 daily**, **8 weekly**, **6 monthly** (offsite).
- Encrypted with age/GPG before upload (`age -e -r <key>`) so backups at
  rest are unreadable without the key. Key material is stored separately
  from the backups (secret manager).

### WAL archiving / PITR (production infrastructure)

- `wal_level = replica`, `archive_mode = on`,
  `archive_command` ships completed WAL segments to object storage
  (`archive_wal/%p`) every segment (~16 MB).
- Continuous archiving gives point-in-time recovery: restore the base
  backup, apply WAL segments up to the target time.
- Retention: 14 days of WAL (aligned with the logical RPO of 15 min).

### Scheduling

- `cron: 01:30 UTC daily pg_dump` (low traffic window), plus a
  `pg_basebackup` weekly for a physical base when WAL archiving is enabled.
- Verify `archive_command` failures are alerted immediately (missing WAL
  degrades PITR silently).

## Object storage backups

- Enable **versioning** on the evidence bucket (accidental overwrite/deletion
  is recoverable).
- **Lifecycle policy:** retain all versions 30 days, then prune old
  versions; move artifacts older than the retention policy to
  cold/archive class.
- **Replication:** cross-region replication of the evidence bucket where the
  provider supports it.
- Evidence artifacts are content-addressed by hash; a corrupted object is
  detected by verification and re-uploadable from another replica or
  regeneration from PostgreSQL state.

## Configuration backups

Back up (to a separate Git repo / secret manager, never committed):

- environment configuration templates (`deployments/compose/.env.example`)
- migration state (embedded in the binary — schema_migrations table is in
  the DB backup)
- encryption key metadata (key version, key id — the master key itself
  lives in the secret manager)
- infrastructure definitions (docker-compose, Terraform if used)

## Backup verification

> A backup that has never been restored is not a backup strategy.

Monthly (and after any schema change):

1. Restore the latest logical backup into an isolated PostgreSQL instance.
2. Run `migrate status` and verify the schema version matches production.
3. Verify record counts: users, organizations, monitors, incidents,
   evidence_records.
4. **Verify evidence hashes**: for a sample of finalized records, fetch the
   artifact from object storage and check `sha256sum` matches
   `evidence_records.hash`. Fail loudly on mismatch.
5. Run the integration test suite against the restored database.
6. Exercise `GET /v1/evidence/{id}/verify` for the sampled records.

Automate with a CI job that runs steps 1–4 nightly on a scratch instance.

## Restore procedure

```
1. Provision a new PostgreSQL (same major version).
2. Restore the base backup:
     pg_restore -d newdb --no-owner --no-privileges backup.dump
   (or: restore physical base + replay WAL to target time for PITR)
3. Apply any migrations newer than the backup.
4. Point the API at the restored database (config change, rolling restart).
5. Verify health/ready, sample queries, incident + evidence lookups.
6. Run backup verification steps 3–5.
```

## Failure scenarios

See `docs/disaster-recovery/runbook.md` for detection/mitigation/recovery of
each scenario, including whole-region failure and accidental deletion.
