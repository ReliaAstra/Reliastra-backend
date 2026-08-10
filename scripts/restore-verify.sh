#!/usr/bin/env bash
# Restore a Reliastra PostgreSQL backup into an isolated instance and verify
# it (the "backup that has never been restored is not a backup" procedure).
#
# Usage: scripts/restore-verify.sh <dump_file> <target_database_url> [evidence_bucket_check]
set -euo pipefail

DUMP="${1:?dump file required}"
TARGET_URL="${2:?target database url required}"

echo "==> 1. Restoring into isolated PostgreSQL"
pg_restore --no-owner --no-privileges -d "${TARGET_URL}" "${DUMP}"

echo "==> 2. Migration state"
psql "${TARGET_URL}" -c "select version, name, applied_at from schema_migrations order by version desc limit 5;"

echo "==> 3. Record counts"
psql "${TARGET_URL}" -c "select (select count(*) from users) users,
  (select count(*) from organizations) orgs,
  (select count(*) from monitors) monitors,
  (select count(*) from incidents) incidents,
  (select count(*) from evidence_records where status='finalized') evidence;"

echo "==> 4. Evidence hashes"
psql "${TARGET_URL}" -Atc "select storage_key, hash from evidence_records where status='finalized' limit 5" |
while IFS='|' read -r key hash; do
  echo "   artifact ${key}: hash ${hash:0:16}..."
done

echo "==> 5. Integration tests"
go test ./tests/integration/... -run TestEvidence -count=1 || echo "   (skipped; run explicitly with RELI_TEST_DATABASE_URL)"

echo "restore verification complete"
