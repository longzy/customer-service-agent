"""handoffs 唯一约束

Revision ID: 0005_handoff_unique
Revises: 0004_handoffs
Create Date: 2026-11-16
"""

from alembic import op

revision = "0005_handoff_unique"
down_revision = "0004_handoffs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_handoff_conversation",
        "handoffs",
        ["tenant_id", "user_id", "conversation_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_handoff_conversation", "handoffs", type_="unique")
