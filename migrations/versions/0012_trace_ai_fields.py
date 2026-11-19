"""Trace 与 AI 事件的扩展字段

Revision ID: 0012_trace_ai_fields
Revises: 0011_service_audit_events
Create Date: 2026-11-19
"""

import sqlalchemy as sa
from alembic import op

revision = "0012_trace_ai_fields"
down_revision = "0011_service_audit_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tool_executions", sa.Column("span_id", sa.String(16), nullable=True))
    op.add_column("tool_executions", sa.Column("parent_span_id", sa.String(16), nullable=True))
    op.add_column("tool_executions", sa.Column("step", sa.String(32), nullable=True))
    op.add_column(
        "tool_executions",
        sa.Column("sampled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "tool_executions",
        sa.Column("source", sa.String(16), nullable=False, server_default=sa.text("'buffered'")),
    )

    op.add_column("service_ai_events", sa.Column("prompt_version", sa.String(32), nullable=True))
    op.add_column("service_ai_events", sa.Column("prompt_hash", sa.String(64), nullable=True))
    op.add_column("service_ai_events", sa.Column("model", sa.String(64), nullable=True))
    op.add_column("service_ai_events", sa.Column("input_tokens", sa.Integer(), nullable=True))
    op.add_column("service_ai_events", sa.Column("output_tokens", sa.Integer(), nullable=True))
    op.add_column(
        "service_ai_events", sa.Column("first_token_latency_ms", sa.Integer(), nullable=True)
    )
    op.add_column(
        "service_ai_events",
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("service_ai_events", "retry_count")
    op.drop_column("service_ai_events", "first_token_latency_ms")
    op.drop_column("service_ai_events", "output_tokens")
    op.drop_column("service_ai_events", "input_tokens")
    op.drop_column("service_ai_events", "model")
    op.drop_column("service_ai_events", "prompt_hash")
    op.drop_column("service_ai_events", "prompt_version")

    op.drop_column("tool_executions", "source")
    op.drop_column("tool_executions", "sampled")
    op.drop_column("tool_executions", "step")
    op.drop_column("tool_executions", "parent_span_id")
    op.drop_column("tool_executions", "span_id")
