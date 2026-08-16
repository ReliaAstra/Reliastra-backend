"""add_timeline_indexes

Add composite indexes on the observations table to support the
vendor timeline endpoint efficiently:
  - (endpoint_url, timestamp)  for per-vendor time-range lookups
  - (source_type, endpoint_url, timestamp) for the timeline query predicate
  - (endpoint_url, region, timestamp) for future multi-region support

Revision ID: 0010_timeline_indexes
Revises: a5dcf0a1e6f1
Create Date: 2026-08-16 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0010_timeline_indexes"
down_revision: Union[str, None] = "a5dcf0a1e6f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Composite index for the most common timeline query pattern
    op.create_index(
        "ix_obs_endpoint_ts",
        "observations",
        ["endpoint_url", "timestamp"],
    )
    # Composite index including source_type (the timeline filters on it)
    op.create_index(
        "ix_obs_source_endpoint_ts",
        "observations",
        ["source_type", "endpoint_url", "timestamp"],
    )
    # Composite index for region-scoped queries
    op.create_index(
        "ix_obs_endpoint_region_ts",
        "observations",
        ["endpoint_url", "region", "timestamp"],
    )


def downgrade() -> None:
    op.drop_index("ix_obs_endpoint_ts", table_name="observations")
    op.drop_index("ix_obs_source_endpoint_ts", table_name="observations")
    op.drop_index("ix_obs_endpoint_region_ts", table_name="observations")
