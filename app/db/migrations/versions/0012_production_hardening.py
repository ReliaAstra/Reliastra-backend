"""production_hardening

Production-hardening fixes from the platform reliability review:

1. ``users.is_system_admin`` column — the model declared it but no
   migration ever added it (boot drift that broke the admin seed path).
2. ``check_results`` monthly partitions for the next 12 months
   (FIX 5) — the parent table is PARTITION BY RANGE (executed_at) and only
   a DEFAULT partition existed.
3. Partial index on ``dependencies.next_check_at`` (FIX 24) — the
   ``get_due_dependencies`` scan only reads active, non-deleted rows.
4. ``observation_outbox`` table (FIX 9) — transactional outbox for the
   observation dual-write.
5. Refresh-token family columns ``token_family`` / ``token_sequence``
   (FIX 28) — rotation + replay detection.

Revision ID: 0012_production_hardening
Revises: 0011_plg_growth_features
Create Date: 2026-08-17 00:00:00.000000

"""
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0012_production_hardening"
down_revision: Union[str, None] = "0011_plg_growth_features"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _partition_months(count: int = 12) -> list[tuple[str, datetime, datetime]]:
    """Monthly partition boundaries starting at the current month."""
    now = datetime.now(timezone.utc)
    months: list[tuple[str, datetime, datetime]] = []
    year, month = now.year, now.month
    for _ in range(count):
        start = datetime(year, month, 1, tzinfo=timezone.utc)
        if month == 12:
            end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
        months.append((f"check_results_{start:%Y_%m}", start, end))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def upgrade() -> None:
    # 1. users admin/growth columns (model/migration drift fix — the User
    #    model declares these but no earlier migration ever created them)
    op.add_column(
        "users",
        sa.Column(
            "is_system_admin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column("users", sa.Column("admin_note", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("source", sa.String(50), nullable=True))
    op.add_column(
        "users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "login_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
    )

    # 2. Monthly check_results partitions (FIX 5)
    for name, start, end in _partition_months(12):
        op.execute(
            f"CREATE TABLE IF NOT EXISTS {name} "
            f"PARTITION OF check_results "
            f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')"
        )

    # 3. Partial index for due-dependency scans (FIX 24)
    op.execute(
        "CREATE INDEX idx_dependencies_next_check_at_due "
        "ON dependencies (next_check_at) "
        "WHERE is_active = TRUE AND is_deleted = FALSE"
    )

    # 4. observation_outbox (FIX 9)
    op.create_table(
        "observation_outbox",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_observation_outbox_created_at",
        "observation_outbox",
        ["created_at"],
    )

    # 5. Refresh token family (FIX 28)
    op.add_column(
        "refresh_tokens",
        sa.Column(
            "token_family",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "refresh_tokens",
        sa.Column(
            "token_sequence",
            sa.Integer(),
            nullable=True,
        ),
    )
    # Backfill: each existing token becomes its own family at sequence 1.
    op.execute(
        "UPDATE refresh_tokens "
        "SET token_family = id, token_sequence = 1 "
        "WHERE token_family IS NULL OR token_sequence IS NULL"
    )
    op.alter_column("refresh_tokens", "token_family", nullable=False)
    op.alter_column(
        "refresh_tokens",
        "token_sequence",
        nullable=False,
        server_default=sa.text("1"),
    )
    op.create_index(
        "ix_refresh_tokens_token_family",
        "refresh_tokens",
        ["token_family"],
    )


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_token_family", table_name="refresh_tokens")
    op.drop_column("refresh_tokens", "token_sequence")
    op.drop_column("refresh_tokens", "token_family")

    op.drop_index("ix_observation_outbox_created_at", table_name="observation_outbox")
    op.drop_table("observation_outbox")

    op.execute("DROP INDEX IF EXISTS idx_dependencies_next_check_at_due")

    for name, _start, _end in _partition_months(12):
        op.execute(f"DROP TABLE IF EXISTS {name}")

    op.drop_column("users", "login_count")
    op.drop_column("users", "last_activity_at")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "source")
    op.drop_column("users", "admin_note")
    op.drop_column("users", "is_system_admin")
