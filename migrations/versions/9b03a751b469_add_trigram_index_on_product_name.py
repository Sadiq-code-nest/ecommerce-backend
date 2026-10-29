"""add trigram index on product name

Revision ID: 9b03a751b469
Revises: 7ae413a239ce
Create Date: 2026-10-29 14:36:16.492705

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b03a751b469'
down_revision: Union[str, Sequence[str], None] = '7ae413a239ce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE INDEX ix_products_name_trgm ON products USING gin (name gin_trgm_ops)")


def downgrade() -> None:
    op.execute("DROP INDEX ix_products_name_trgm")
