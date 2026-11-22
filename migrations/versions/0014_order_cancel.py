"""订单取消：确认事实与同订单活跃任务唯一约束

Revision ID: 0014_order_cancel
Revises: 0013_order_query
Create Date: 2026-11-22

只加法：
- `cancellation_requests` 新增发起人（`requested_by_type`/`requested_by_id`）、
  客户确认（`confirmed_at`/`confirmation_source`/`confirmed_by_id`）；旧数据按
  客户发起回填。
- 部分唯一索引 `uq_cancellation_active_order`：同一租户同一订单只允许一个进行中
  的取消任务（谓词与 `domain.cancellation.IN_PROGRESS_STATES` 一致）。

迁移前若旧数据存在同订单多个进行中任务，保留最新一条，其余收尾为 ABANDONED，
否则部分唯一索引无法创建。
"""

import sqlalchemy as sa
from alembic import op

revision = "0014_order_cancel"
down_revision = "0013_order_query"
branch_labels = None
depends_on = None

ACTIVE_PREDICATE = (
    "state IN ('COLLECTING','AWAITING_CONFIRMATION','SUBMITTING','SUBMIT_UNKNOWN','ACCEPTED')"
)


def upgrade() -> None:
    op.add_column(
        "cancellation_requests",
        sa.Column("requested_by_type", sa.String(16), nullable=True),
    )
    op.add_column(
        "cancellation_requests",
        sa.Column("requested_by_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "cancellation_requests",
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "cancellation_requests",
        sa.Column("confirmation_source", sa.String(16), nullable=True),
    )
    op.add_column(
        "cancellation_requests",
        sa.Column("confirmed_by_id", sa.String(64), nullable=True),
    )
    op.execute(
        "update cancellation_requests "
        "set requested_by_type = 'CUSTOMER', requested_by_id = user_id "
        "where requested_by_type is null"
    )
    # 旧原型可能残留同订单多个进行中任务；按状态推进程度保留最靠后的一条，
    # 再按创建时间，其余收尾后再建唯一索引。
    op.execute(
        "with ranked as ("
        "  select id, row_number() over ("
        "    partition by tenant_id, order_id "
        "    order by case state "
        "      when 'ACCEPTED' then 5 "
        "      when 'SUBMIT_UNKNOWN' then 4 "
        "      when 'SUBMITTING' then 3 "
        "      when 'AWAITING_CONFIRMATION' then 2 "
        "      else 1 end desc, "
        "    created_at desc, id desc"
        "  ) as rn"
        "  from cancellation_requests "
        "  where state IN "
        "('COLLECTING','AWAITING_CONFIRMATION','SUBMITTING','SUBMIT_UNKNOWN','ACCEPTED')"
        ") "
        "update cancellation_requests "
        "set state = 'ABANDONED', version = version + 1 "
        "where id in (select id from ranked where rn > 1)"
    )
    op.create_index(
        "uq_cancellation_active_order",
        "cancellation_requests",
        ["tenant_id", "order_id"],
        unique=True,
        postgresql_where=sa.text(ACTIVE_PREDICATE),
    )


def downgrade() -> None:
    op.drop_index("uq_cancellation_active_order", table_name="cancellation_requests")
    op.drop_column("cancellation_requests", "confirmed_by_id")
    op.drop_column("cancellation_requests", "confirmation_source")
    op.drop_column("cancellation_requests", "confirmed_at")
    op.drop_column("cancellation_requests", "requested_by_id")
    op.drop_column("cancellation_requests", "requested_by_type")
