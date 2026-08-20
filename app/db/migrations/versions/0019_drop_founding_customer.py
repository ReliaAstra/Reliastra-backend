"""Drop the founding customer program columns from organizations.

The founding customer program (private 25-spot, 40% lifetime discount) has
been retired: its billing endpoints, admin listing and discount logic are
removed from the application, so the supporting columns are dropped.

Revision ID: 0019_drop_founding_customer
Revises: 0018_lean_partner_referral
Create Date: 2026-08-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0019_drop_founding_customer"
down_revision: Union[str, None] = "0018_lean_partner_referral"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {col["name"] for col in inspector.get_columns("organizations")}

    for column in ("founding_discount_pct", "is_founding_customer"):
        if column in existing:
            op.drop_column("organizations", column)


def downgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "is_founding_customer",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "founding_discount_pct",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
