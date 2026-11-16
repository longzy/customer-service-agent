"""trace 与审计

Revision ID: 0006_trace_audit
Revises: 0005_handoff_unique
Create Date: 2026-11-16
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_trace_audit"
down_revision = "0005_handoff_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cancellation_requests",
        sa.Column(
            "trace_id",
            sa.String(36),
            nullable=False,
            server_default=sa.text("gen_random_uuid()::text"),
        ),
    )
    op.create_index("ix_cancellation_requests_trace_id", "cancellation_requests", ["trace_id"])
    op.create_table(
        "tool_executions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("trace_id", sa.String(36), nullable=False, index=True),
        sa.Column("tool_name", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("user_id", sa.String(64), nullable=False, index=True),
        sa.Column("order_id", sa.String(64), nullable=True),
        sa.Column("idempotency_key_digest", sa.String(32), nullable=True),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("result_status", sa.String(16), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(32), nullable=True),
        sa.Column("response_redacted", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("trace_id", sa.String(36), nullable=False, index=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("order_id", sa.String(64), nullable=True),
        sa.Column("idempotency_key_digest", sa.String(32), nullable=True),
        sa.Column("result_status", sa.String(16), nullable=False),
        sa.Column("metadata_redacted", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("tool_executions")
    op.drop_index("ix_cancellation_requests_trace_id", table_name="cancellation_requests")
    op.drop_column("cancellation_requests", "trace_id")
