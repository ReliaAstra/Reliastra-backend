"""soft_delete_members_api_keys

Add SoftDeleteMixin columns (is_deleted, deleted_at) to organization_members
and api_keys so revoke/remove is recoverable.

Revision ID: 0017_soft_delete_members_keys
Revises: 0016_partner_network
Create Date: 2026-08-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0017_soft_delete_members_keys"
down_revision: Union[str, None] = "0016_partner_network"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Model already declared this column; it was never migrated.
    op.add_column(
        "users",
        sa.Column("external_auth_id", sa.String(255), nullable=True),
    )
    op.create_index(
        "ix_users_external_auth_id",
        "users",
        ["external_auth_id"],
        unique=False,
    )

    op.add_column(
        "organization_members",
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "organization_members",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_organization_members_is_deleted",
        "organization_members",
        ["is_deleted"],
    )

    op.add_column(
        "api_keys",
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "api_keys",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_api_keys_is_deleted", "api_keys", ["is_deleted"])


def downgrade() -> None:
    op.drop_index("ix_api_keys_is_deleted", table_name="api_keys")
    op.drop_column("api_keys", "deleted_at")
    op.drop_column("api_keys", "is_deleted")

    op.drop_index(
        "ix_organization_members_is_deleted", table_name="organization_members"
    )
    op.drop_column("organization_members", "deleted_at")
    op.drop_column("organization_members", "is_deleted")
