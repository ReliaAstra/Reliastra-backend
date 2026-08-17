"""enforce one open incident per dependency

Revision ID: 0014_open_incident_unique
Revises: 0013_missing_model_tables
Create Date: 2026-08-17

Quorum evaluation is read-then-write (non-atomic). Under concurrent region
checks, multiple sessions can all observe "no open incident" and each create
one, producing duplicate incidents (measured: 5 incidents from 12 concurrent
checks). This partial unique index makes the invariant
"at most one OPEN incident per dependency" an enforced DB constraint so the
service layer can convert the race into a clean upsert.
"""
from alembic import op

revision = "0014_open_incident_unique"
down_revision = "0013_missing_model_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Historical races may have created duplicate OPEN incidents for the same
    # dependency.  Resolve the newer duplicates (keep the earliest) so the
    # unique index can be created.  The kept incident remains the canonical
    # open incident; resolved duplicates are idempotently ignored downstream.
    op.execute(
        """
        UPDATE incidents AS dup
        SET status = 'resolved',
            resolved_at = COALESCE(dup.resolved_at, dup.started_at),
            description = COALESCE(
                dup.description,
                '') || ' [auto-resolved duplicate incident during migration]'
        WHERE dup.status = 'open'
          AND dup.id IN (
              SELECT i.id FROM (
                  SELECT id,
                         row_number() OVER (
                             PARTITION BY org_id, dependency_id
                             ORDER BY started_at ASC, id ASC
                         ) AS rn
                  FROM incidents
                  WHERE status = 'open'
              ) i
              WHERE i.rn > 1
          );
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_incidents_one_open_per_dependency
        ON incidents (org_id, dependency_id)
        WHERE status = 'open';
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS uq_incidents_one_open_per_dependency;"
    )
