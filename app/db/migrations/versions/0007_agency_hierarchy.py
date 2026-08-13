"""Add agency client/application hierarchy.

Revision ID: 0007_agency_hierarchy
Revises: 0006_evidence_snapshots
Create Date: 2026-08-12
"""

import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_agency_hierarchy"
down_revision = "0006_evidence_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_clients_org_id", "clients", ["org_id"])
    op.create_table(
        "applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_applications_org_id", "applications", ["org_id"])
    op.create_index("ix_applications_client_id", "applications", ["client_id"])

    op.add_column(
        "organizations",
        sa.Column(
            "has_agency_mode",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "dependencies",
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_dependencies_application_id", "dependencies", ["application_id"]
    )
    op.create_foreign_key(
        "fk_dependencies_application_id_applications",
        "dependencies",
        "applications",
        ["application_id"],
        ["id"],
        ondelete="SET NULL",
    )

    bind = op.get_bind()
    organizations = sa.table(
        "organizations", sa.column("id", postgresql.UUID(as_uuid=True))
    )
    applications = sa.table(
        "applications",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("org_id", postgresql.UUID(as_uuid=True)),
        sa.column("client_id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String()),
        sa.column("description", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    dependencies = sa.table(
        "dependencies",
        sa.column("org_id", postgresql.UUID(as_uuid=True)),
        sa.column("application_id", postgresql.UUID(as_uuid=True)),
    )
    now = datetime.now(timezone.utc)
    for row in bind.execute(sa.select(organizations.c.id)):
        application_id = uuid.uuid4()
        bind.execute(
            applications.insert().values(
                id=application_id,
                org_id=row.id,
                client_id=None,
                name="Default",
                description="Default application for existing dependencies",
                created_at=now,
                updated_at=now,
            )
        )
        bind.execute(
            dependencies.update()
            .where(dependencies.c.org_id == row.id)
            .values(application_id=application_id)
        )


def downgrade() -> None:
    op.drop_constraint(
        "fk_dependencies_application_id_applications",
        "dependencies",
        type_="foreignkey",
    )
    op.drop_index("ix_dependencies_application_id", table_name="dependencies")
    op.drop_column("dependencies", "application_id")
    op.drop_column("organizations", "has_agency_mode")
    op.drop_table("applications")
    op.drop_table("clients")
