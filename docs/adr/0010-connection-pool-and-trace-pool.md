# ADR-0010：连接池参数与 Trace 独立小池

- 状态：已批准
- 日期：2026-11-19
- 批准：2026-11-19（用户确认连接池收口）
- 关联：[总体架构](../architecture/overview.md) 第 5 节、[ADR-0009](0009-request-unit-of-work.md)

## 背景

`create_async_engine` 原先只设置 `pool_pre_ping=True`，其余参数全部使用 SQLAlchemy 默认值：`pool_size=5`、`max_overflow=10`、`pool_timeout=30`、`pool_recycle=-1`。同时存在两个问题：

1. **Trace 与业务共享连接池**。`AsyncTraceSink` 每次 `start`/`finish` 都新开 session 并立即提交。工具调用期间，业务请求已经占着一条连接，Trace 写又需要第二条；池满时 Trace 等 30s，而 `future.result(timeout=5)` 5s 就放弃并抛 `TraceSinkError`。
2. **模型调用长时间占连接**。客户消息在 `flush` 后等待模型返回（默认 10s），事务保持打开，连接不释放。并发消息数接近池上限时，新请求开始排队。

Trace 是辅助可观测数据，业务请求是必须成功的主链路。两者共用池会让辅助数据抢主链路的连接，也会形成「业务请求占连接 → 等自己的 Trace 写 → Trace 等业务释放」的等待链。

## 决策

### 1. 池参数进 Settings

```text
db_pool_size=5
db_max_overflow=10
db_pool_timeout=30
db_pool_recycle=1800
trace_pool_size=2
trace_max_overflow=2
trace_pool_timeout=2
```

测试环境仍用 `NullPool`，避免 TestClient 跨事件循环复用连接。

### 2. Trace 使用独立 engine 与小池

`platform/db.py` 新增 `trace_engine` 与 `trace_session_factory`；`AsyncTraceSink` 只接收后者。业务请求和 Trace 写不再共享连接，也不互相等待。

Trace 池保持小：写入是单行 `INSERT`/`UPDATE`，并发由工具调用触发，2+2 条足够；池小同时形成背压，限制 Trace 对数据库的冲击。池满时按 2s 快速失败，而不是等业务池的 30s。

### 3. 容量公式

每个 worker 的连接上限：

```text
db_pool_size + db_max_overflow + trace_pool_size + trace_max_overflow = 19
```

部署时需满足：

```text
workers × 19 + 运维余量 ≤ PostgreSQL max_connections
```

单 worker 默认 19；5 个 worker 约 95，已接近 PostgreSQL 默认 100，需要调大 `max_connections` 或减小池。

## 后果

- 业务请求和 Trace 写故障隔离；Trace 慢不再拖住业务取连接。
- 总连接数增加 4 条/worker，部署时必须按公式核算。
- Trace 池满时仍会抛 `TraceSinkError`，当前语义仍是失败关闭（工具执行记录被视为可追溯数据）。若要彻底不影响业务，需要另立决策把 Trace 降级为 best-effort。
- 模型调用期间连接仍被占用；要缩短占用，需要把模型调用移出事务，属于后续切片。

## 拒绝的方案

- **共享业务池**：现状，自竞争与 30s 等待。
- **Trace 用 NullPool**：每次新建连接，延迟与握手成本高。
- **Trace 改后台队列/批量写**：M1 的工具调用量小，引入队列的运维成本高于收益；后续量级上来再评估。
- **把 `pool_timeout` 直接调小到 2s 给业务池**：业务请求在高峰会更容易 500，不能替代 Trace 隔离。
