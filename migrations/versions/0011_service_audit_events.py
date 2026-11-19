"""M1 审计事件表与只追加约束

Revision ID: 0011_service_audit_events
Revises: 0010_service_employee_auth
Create Date: 2026-11-19
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_service_audit_events"
down_revision = "0010_service_employee_auth"
branch_labels = None
depends_on = None

APPEND_ONLY_FUNCTION = "service_audit_events_append_only"


def upgrade() -> None:
    op.create_table(
        "service_audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("result_status", sa.String(16), nullable=False),
        sa.Column("journey_id", sa.String(36), nullable=True),
        sa.Column("trace_id", sa.String(36), nullable=False, index=True),
        sa.Column("metadata_redacted", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_service_audit_events_journey_created_at",
        "service_audit_events",
        ["journey_id", "created_at"],
    )
    op.create_index(
        "ix_service_audit_events_event_type_created_at",
        "service_audit_events",
        ["event_type", "created_at"],
    )
    # 审计只追加：行级 UPDATE/DELETE 一律失败；清理只能由表所有者 TRUNCATE/DDL 完成。
    op.execute(
        f"""
        CREATE FUNCTION {APPEND_ONLY_FUNCTION}() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'service_audit_events is append-only';
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER service_audit_events_no_update
        BEFORE UPDATE ON service_audit_events
        FOR EACH ROW EXECUTE FUNCTION {APPEND_ONLY_FUNCTION}()
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER service_audit_events_no_delete
        BEFORE DELETE ON service_audit_events
        FOR EACH ROW EXECUTE FUNCTION {APPEND_ONLY_FUNCTION}()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS service_audit_events_no_delete ON service_audit_events")
    op.execute("DROP TRIGGER IF EXISTS service_audit_events_no_update ON service_audit_events")
    op.execute(f"DROP FUNCTION IF EXISTS {APPEND_ONLY_FUNCTION}()")
    op.drop_index("ix_service_audit_events_event_type_created_at", "service_audit_events")
    op.drop_index("ix_service_audit_events_journey_created_at", "service_audit_events")
    op.drop_table("service_audit_events")
