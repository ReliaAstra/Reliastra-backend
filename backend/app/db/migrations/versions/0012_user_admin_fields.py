"""add missing user admin panel columns

Revision ID: 0012_user_admin_fields
Revises: 0011_plg_growth_features
Create Date: 2026-08-17

The User ORM model declares ``is_system_admin`` and ``admin_note`` (used by
the admin panel) but no migration ever created them.  Every ``SELECT`` on
``users`` (register, login, auth) fails with
``column users.is_system_admin does not exist``.
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_user_admin_fields"
down_revision = "0011_plg_growth_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_system_admin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "users",
        sa.Column("admin_note", sa.Text(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("source", sa.String(50), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "login_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "login_count")
    op.drop_column("users", "last_activity_at")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "source")
    op.drop_column("users", "admin_note")
    op.drop_column("users", "is_system_admin")
