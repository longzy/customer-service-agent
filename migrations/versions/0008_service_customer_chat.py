"""客户消息、AI 事件与交接单

Revision ID: 0008_service_customer_chat
Revises: 0007_service_customer_auth
Create Date: 2026-11-17
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_service_customer_chat"
down_revision = "0007_service_customer_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_messages",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("service_conversations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("author_type", sa.String(16), nullable=False),
        sa.Column("author_id", sa.String(36), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("trace_id", sa.String(36), nullable=False, index=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_service_messages_conversation_id_id",
        "service_messages",
        ["conversation_id", "id"],
    )
    op.create_table(
        "service_ai_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("service_conversations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("journey_id", sa.String(36), nullable=False, index=True),
        sa.Column("event_type", sa.String(16), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("trace_id", sa.String(36), nullable=False, index=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_table(
        "service_handoffs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("service_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            sa.String(36),
            sa.ForeignKey("service_customers.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False, server_default=sa.text("'normal'")),
        sa.Column("summary", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("context", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("pending_step", sa.Text(), nullable=True),
        sa.Column("claimed_by", sa.String(36), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("journey_id", sa.String(36), nullable=False, index=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_service_handoffs_status_created_at",
        "service_handoffs",
        ["status", "created_at"],
    )
    op.create_index(
        "uq_service_handoffs_open_conversation",
        "service_handoffs",
        ["tenant_id", "conversation_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('QUEUED', 'CLAIMED', 'ACTIVE')"),
    )


def downgrade() -> None:
    op.drop_index("uq_service_handoffs_open_conversation", table_name="service_handoffs")
    op.drop_index("ix_service_handoffs_status_created_at", table_name="service_handoffs")
    op.drop_table("service_handoffs")
    op.drop_table("service_ai_events")
    op.drop_index("ix_service_messages_conversation_id_id", table_name="service_messages")
    op.drop_table("service_messages")
