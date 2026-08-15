"""merge_heads

Revision ID: a5dcf0a1e6f1
Revises: 0003_email_verification, 0009_founding_customer
Create Date: 2026-08-15 22:22:49.440755

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a5dcf0a1e6f1'
down_revision: Union[str, None] = ('0003_email_verification', '0009_founding_customer')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
