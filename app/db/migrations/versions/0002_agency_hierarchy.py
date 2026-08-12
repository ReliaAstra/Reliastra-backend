"""add agency hierarchy (clients, applications) and dependency.application_id

Revision ID: 0002_agency_hierarchy
Revises: 0001_initial
Create Date: 2026-08-12 00:01:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002_agency_hierarchy"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. clients
    op.create_table(
        "clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_clients_org_id"), "clients", ["org_id"])

    # 2. applications
    op.create_table(
        "applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="SET NULL"),
    )
    op.create_index(op.f("ix_applications_org_id"), "applications", ["org_id"])
    op.create_index(op.f("ix_applications_client_id"), "applications", ["client_id"])

    # 3. dependencies.application_id (nullable; backfilled via data migration)
    op.add_column(
        "dependencies",
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_dependencies_application_id",
        "dependencies",
        "applications",
        ["application_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_dependencies_application_id"), "dependencies", ["application_id"]
    )

    # 4. organizations.has_agency_mode
    op.add_column(
        "organizations",
        sa.Column(
            "has_agency_mode",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("organizations", "has_agency_mode")
    op.drop_index(op.f("ix_dependencies_application_id"), table_name="dependencies")
    op.drop_constraint(
        "fk_dependencies_application_id", "dependencies", type_="foreignkey"
    )
    op.drop_column("dependencies", "application_id")
    op.drop_table("applications")
    op.drop_table("clients")
