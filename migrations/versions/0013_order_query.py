"""订单查询：客户 OMS 身份与消息订单快照

Revision ID: 0013_order_query
Revises: 0012_trace_ai_fields
Create Date: 2026-11-20

只加法：
- `service_customers.oms_customer_id`：客户账号在 OMS 侧的客户 ID，订单归属只按它判定；
  未绑定为空，查询统一"查无此单"。
- `service_messages.payload`：AI 消息的订单摘要快照（白名单字段），刷新/重放不重查 OMS。
"""

import sqlalchemy as sa
from alembic import op

revision = "0013_order_query"
down_revision = "0012_trace_ai_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "service_customers",
        sa.Column("oms_customer_id", sa.String(64), nullable=True),
    )
    op.create_index(
        "uq_service_customers_tenant_oms",
        "service_customers",
        ["tenant_id", "oms_customer_id"],
        unique=True,
        postgresql_where=sa.text("oms_customer_id IS NOT NULL"),
    )
    op.add_column("service_messages", sa.Column("payload", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("service_messages", "payload")
    op.drop_index("uq_service_customers_tenant_oms", table_name="service_customers")
    op.drop_column("service_customers", "oms_customer_id")
