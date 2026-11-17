"""客户账号、客户 session、会话与限速桶

Revision ID: 0007_service_customer_auth
Revises: 0006_trace_audit
Create Date: 2026-11-17
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_service_customer_auth"
down_revision = "0006_trace_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_customers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("display_name", sa.String(64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("tenant_id", "username", name="uq_service_customers_tenant_username"),
    )
    op.create_table(
        "service_customer_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "customer_id",
            sa.String(36),
            sa.ForeignKey("service_customers.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_service_customer_sessions_token_hash",
        "service_customer_sessions",
        ["token_hash"],
        unique=True,
    )
    op.create_table(
        "service_conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column(
            "customer_id",
            sa.String(36),
            sa.ForeignKey("service_customers.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("assigned_employee_id", sa.String(36), nullable=True),
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
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "uq_service_conversations_open_customer",
        "service_conversations",
        ["tenant_id", "customer_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'CLOSED'"),
    )
    op.create_table(
        "service_rate_limit_buckets",
        sa.Column("bucket_key", sa.String(160), primary_key=True),
        sa.Column("window_start", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_table("service_rate_limit_buckets")
    op.drop_index("uq_service_conversations_open_customer", table_name="service_conversations")
    op.drop_table("service_conversations")
    op.drop_index("ix_service_customer_sessions_token_hash", table_name="service_customer_sessions")
    op.drop_table("service_customer_sessions")
    op.drop_table("service_customers")
