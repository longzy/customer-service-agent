"""handoffs

Revision ID: 0004_handoffs
Revises: 0003_cancel_version
Create Date: 2026-11-15
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_handoffs"
down_revision = "0003_cancel_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "handoffs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), nullable=False, index=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("user_id", sa.String(64), nullable=False, index=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("trace_id", sa.String(36), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("handoffs")
