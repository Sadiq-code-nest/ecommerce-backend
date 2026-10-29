"""partial unique index on active product names

Revision ID: 7ae413a239ce
Revises: f99f6048fdf8
Create Date: 2026-10-29 14:09:02.600770

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7ae413a239ce'
down_revision: Union[str, Sequence[str], None] = 'f99f6048fdf8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("uq_products_name_lower", table_name="products")
    op.create_index(
        "uq_products_name_lower", "products", [sa.literal_column("lower(name)")],
        unique=True, postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_index("uq_products_name_lower", table_name="products")
    op.create_index(
        "uq_products_name_lower", "products", [sa.literal_column("lower(name)")], unique=True
    )