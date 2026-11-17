"""客户消息幂等键

Revision ID: 0009_message_idempotency
Revises: 0008_service_customer_chat
Create Date: 2026-11-17
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_message_idempotency"
down_revision = "0008_service_customer_chat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "service_messages",
        sa.Column("idempotency_key", sa.String(64), nullable=True),
    )
    op.create_index(
        "uq_service_messages_idempotency",
        "service_messages",
        ["conversation_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_service_messages_idempotency", table_name="service_messages")
    op.drop_column("service_messages", "idempotency_key")
