"""cancellation_requests

Revision ID: 0002_cancellation
Revises: 0001_conversations
Create Date: 2026-11-15
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_cancellation"
down_revision = "0001_conversations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cancellation_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("user_id", sa.String(64), nullable=False, index=True),
        sa.Column("order_id", sa.String(64), nullable=False, index=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("reason_code", sa.String(32), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("cancellation_requests")
