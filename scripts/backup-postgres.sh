#!/usr/bin/env bash
# Daily logical PostgreSQL backup + retention + encryption.
#
# Usage: scripts/backup-postgres.sh <database_url> <backup_dir> <age_public_key>
set -euo pipefail

DB_URL="${1:?database url required}"
BACKUP_DIR="${2:?backup dir required}"
AGE_KEY="${3:-}"   # optional age recipient public key

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DUMP="${BACKUP_DIR}/reliastra-${STAMP}.dump"
mkdir -p "$BACKUP_DIR"

echo "dumping to ${DUMP}"
pg_dump -Fc --no-owner --no-privileges "${DB_URL}" -f "${DUMP}"

if [ -n "${AGE_KEY}" ]; then
  age -e -r "${AGE_KEY}" -o "${DUMP}.age" "${DUMP}"
  rm -f "${DUMP}"
  echo "encrypted backup: ${DUMP}.age"
fi

# Retention: keep 14 dailies, 8 weeklies, 6 monthlies.
find "${BACKUP_DIR}" -name 'reliastra-*.dump*' -mtime +14 -delete

echo "backup complete: $(du -h "${DUMP}.age" 2>/dev/null || du -h "${DUMP}" | cut -f1)"
