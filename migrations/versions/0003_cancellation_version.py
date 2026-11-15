"""cancellation_requests：版本、关联与联合唯一

Revision ID: 0003_cancel_version
Revises: 0002_cancellation
Create Date: 2026-11-15
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_cancel_version"
down_revision = "0002_cancellation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cancellation_requests",
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "cancellation_requests", sa.Column("conversation_id", sa.String(36), nullable=True)
    )
    op.add_column(
        "cancellation_requests", sa.Column("last_error_code", sa.String(32), nullable=True)
    )
    op.add_column(
        "cancellation_requests", sa.Column("oms_request_id", sa.String(128), nullable=True)
    )
    op.drop_constraint(
        "cancellation_requests_idempotency_key_key",
        "cancellation_requests",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_cancellation_tenant_idempotency",
        "cancellation_requests",
        ["tenant_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_cancellation_tenant_idempotency", "cancellation_requests", type_="unique"
    )
    op.create_unique_constraint(
        "cancellation_requests_idempotency_key_key",
        "cancellation_requests",
        ["idempotency_key"],
    )
    for column in ("oms_request_id", "last_error_code", "conversation_id", "version"):
        op.drop_column("cancellation_requests", column)
