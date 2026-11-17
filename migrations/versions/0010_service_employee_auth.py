"""员工账号与员工 session

Revision ID: 0010_service_employee_auth
Revises: 0009_message_idempotency
Create Date: 2026-11-17
"""

import sqlalchemy as sa
from alembic import op

revision = "0010_service_employee_auth"
down_revision = "0009_message_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_employees",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="agent"),
        sa.Column("display_name", sa.String(64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("tenant_id", "username", name="uq_service_employees_tenant_username"),
    )
    op.create_table(
        "service_employee_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "employee_id",
            sa.String(36),
            sa.ForeignKey("service_employees.id", ondelete="CASCADE"),
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
    )
    op.create_index(
        "ix_service_employee_sessions_token_hash",
        "service_employee_sessions",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_service_employee_sessions_token_hash",
        table_name="service_employee_sessions",
    )
    op.drop_table("service_employee_sessions")
    op.drop_table("service_employees")
