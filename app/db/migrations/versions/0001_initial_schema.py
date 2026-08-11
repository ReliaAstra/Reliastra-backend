"""Create complete MVP schema, monthly-partition parent, and vendor seed data.

Revision ID: 0001
Revises: None
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from alembic import op
from sqlalchemy.dialects.postgresql import insert

from app.db.base import Base, import_all_models
from app.modules.vendors.models import VendorTracking

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

VENDORS = [
    {
        "id": UUID("00000000-0000-4000-8000-000000000001"),
        "vendor_name": "stripe",
        "display_name": "Stripe",
        "endpoint_url": "https://api.stripe.com/v1/",
        "category": "payments",
        "is_public": True,
    },
    {
        "id": UUID("00000000-0000-4000-8000-000000000002"),
        "vendor_name": "auth0",
        "display_name": "Auth0",
        "endpoint_url": "https://status.auth0.com/",
        "category": "auth",
        "is_public": True,
    },
    {
        "id": UUID("00000000-0000-4000-8000-000000000003"),
        "vendor_name": "cloudflare",
        "display_name": "Cloudflare",
        "endpoint_url": "https://www.cloudflare.com/cdn-cgi/trace",
        "category": "cdn",
        "is_public": True,
    },
    {
        "id": UUID("00000000-0000-4000-8000-000000000004"),
        "vendor_name": "openai",
        "display_name": "OpenAI",
        "endpoint_url": "https://api.openai.com/v1/models",
        "category": "ai",
        "is_public": True,
    },
    {
        "id": UUID("00000000-0000-4000-8000-000000000005"),
        "vendor_name": "twilio",
        "display_name": "Twilio",
        "endpoint_url": "https://api.twilio.com/",
        "category": "communications",
        "is_public": True,
    },
]


def upgrade() -> None:
    import_all_models()
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)
    for year in range(2025, 2032):
        for month in range(1, 13):
            start = date(year, month, 1)
            end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
            table = f"check_results_{year}_{month:02d}"
            op.execute(
                f"CREATE TABLE IF NOT EXISTS {table} PARTITION OF check_results "
                f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')"
            )
    op.execute(
        "CREATE TABLE IF NOT EXISTS check_results_default PARTITION OF check_results DEFAULT"
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_audit_log_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs are append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_logs_immutable
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation()
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_check_results_default_executed_at "
        "ON check_results_default (executed_at)"
    )
    bind.execute(
        insert(VendorTracking)
        .values(VENDORS)
        .on_conflict_do_nothing(index_elements=["vendor_name"])
    )


def downgrade() -> None:
    import_all_models()
    bind = op.get_bind()
    op.execute("DROP TABLE IF EXISTS check_results_default")
    Base.metadata.drop_all(bind=bind, checkfirst=True)
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_log_mutation()")
