"""Add metadata_json to facts.

Revision ID: 20250714_add_fact_metadata
Revises: 20250704_add_fact_is_shared
Create Date: 2026-07-14 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20250714_add_fact_metadata"
down_revision: Union[str, None] = "20250704_add_fact_is_shared"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "facts",
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("facts", "metadata_json")
