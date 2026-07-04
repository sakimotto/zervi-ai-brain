"""Add is_shared flag to facts.

Revision ID: 20250704_add_fact_is_shared
Revises: 20250702_add_documents_and_facts
Create Date: 2026-07-04 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20250704_add_fact_is_shared"
down_revision: Union[str, None] = "20250702_add_documents_and_facts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add the shared flag with a default of False.
    op.add_column(
        "facts",
        sa.Column("is_shared", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Existing seeded departmental facts were created under the system user.
    # Mark them as shared so every user can retrieve them.
    op.execute("UPDATE facts SET is_shared = true WHERE user_id = 1")


def downgrade() -> None:
    op.drop_column("facts", "is_shared")
