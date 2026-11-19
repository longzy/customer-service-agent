# ADR-0012：可观测数据分级与 Trace 降级

- 状态：已批准
- 日期：2026-11-19
- 批准：2026-11-19（用户确认按调研结果分层设计；实现分步推进）
- 实现进度：步骤 1–6 已完成（2026-11-19）
- 关联：[调研笔记](../research/customer-service-trace-2026-11-19.md)、[总体架构](../architecture/overview.md) 第 5 节、[ADR-0009](0009-request-unit-of-work.md)、[ADR-0010](0010-connection-pool-and-trace-pool.md)、[ADR-0011](0011-model-failure-degradation.md)

## 背景

当前实现把两类完全不同的数据放进同一个失败语义：

- `tool_executions`：工具调用的技术 trace，用于排障与延迟分析。
- cancel gateway 的 `audit_transition`：审计事件，用于回答“谁在何时对哪条记录做了什么”。

`ToolGateway._record()` 先写审计、再写 trace；两者任一失败都被包成 `TraceSinkError`，由 `api/main.py` 统一映射为 500。结果是：Trace 池满或写库抖动会让业务请求失败；而审计失败又被当成“Trace 失败”处理，无法单独设置可靠性。

行业调研（见关联笔记）给出的稳定做法是分层：

- 业务事实强一致；
- 审计强一致、追加写、长期保留；
- 技术 trace 允许采样、异步、短期保留、可丢；
- AI 质量事件按关键程度分级。

本 ADR 把这一分层固定为项目决策，并给出可落地的实现顺序。

## 决策

### 1. 四层数据与可靠性等级

| 等级 | 数据 | 表/入口 | 可靠性 | 默认保留 |
|---|---|---|---|---|
| L1 业务事实 | 会话、消息、交接单、订单动作结果 | `service_conversations`、`service_messages`、`service_handoffs` | 强一致；失败回滚并返回 5xx | 按业务/合规 |
| L2 审计 | 谁在何时对哪条记录做了什么 | `service_audit_events` | 强一致、追加写、不可改删；失败回滚并返回 503/500 | 180 天起；金融 5–7 年可配 |
| L3 技术 trace | 请求哪一步慢/错/降级 | `tool_executions` | best-effort；失败不影响业务 | 热数据 30 天；异常样本 1 年 |
| L3.5 AI 质量事件 | 意图/置信度/转人工/失败 | `service_ai_events` | 关键事件强一致；普通成功可降级 | 关键 1 年；普通 90 天 |

`trace_id` 在 M1 保持现有 UUID 请求标识；`span_id`/`parent_span_id` 为后续 OTel 兼容预留，不改变现有字段语义。

### 2. 失败行为矩阵

| 失败点 | 错误类型 | 业务响应 | 副作用 |
|---|---|---|---|
| L1 业务写失败 | 现有 `ApiError`/`SQLAlchemyError` | 回滚 + 4xx/5xx | 无 |
| L2 审计写失败（工具路径） | `AuditWriteError` | 回滚 + 503/500 | 无；不得静默成功 |
| L2 审计写失败（HTTP 安全事件） | 现有 `audit_or_503` | 503 | 保持现状 |
| L3 技术 trace 写失败 | `TraceWriteError` | **正常返回** | 结构化日志 + 指标；不阻断 |
| L3.5 关键 AI 事件失败（转人工/失败/低置信） | `AiEventWriteError` | 回滚 + 503/500 | 关键事件不能丢 |
| L3.5 普通 AI 事件失败 | `AiEventWriteError` | 正常返回 | 日志 + 指标 + 采样 |

### 3. 拆分错误类型

在 `backend/platform/observability.py`：

```python
class AuditWriteError(Exception):
    """审计写入失败；业务必须回滚/失败关闭。"""


class TraceWriteError(Exception):
    """技术 trace 写入失败；只记录，不影响业务。"""
```

`TraceSinkError` 不再作为统一类型使用。调用点：

- TraceSink 实现的写入失败 → `TraceWriteError`；`BufferedTraceSink` 的批量写失败只记日志与指标，不向业务抛。
- `SqlAuditWriter` / `audit_or_503` / cancel `audit_transition` → `AuditWriteError`。
- `ToolGateway._record()`：`self._audit(event)` 抛 `AuditWriteError`；`sink.finish/reject` 抛 `TraceWriteError`。
- `api/main.py`：只注册 `AuditWriteError` 的 500/503 处理器；删除 `TraceSinkError` 的全局 500 处理器。

### 4. 技术 trace 写入

技术 trace 采用“采样 → 有界缓冲 → 批量异步写”：

- `SampledTraceSink`：在 `start()` 入口做 head-based 采样，写入 `sampled` 标记。
- `BufferedTraceSink`：有界队列（默认 1000 条），每 2 秒或满 200 条批量写；队列满时丢最旧并计数；应用关闭时 flush。
- 写入使用现有 `trace_session_factory`（独立小池），不占业务事务。
- 失败或丢弃只记录 `trace.write_failed` / `trace.dropped` 与指标，不改变业务响应。

已按此实现：请求线程只入队，writer 在事件循环内批量提交；队列满丢最旧，关闭时 flush。

### 5. 采样

- 100%：`error_code` 非空、handoff、cancel、模型失败、安全事件、工具失败。
- 正常成功：默认 5%，`TRACE_SAMPLE_RATE` 可配。
- 采样决策在请求入口一次完成，随 `trace_id` 传递；不允许半条链。
- 审计不采样；AI 关键事件不采样。

### 6. 字段扩展

`tool_executions` 增加：

| 字段 | 用途 |
|---|---|
| `span_id` | 16 hex，步骤 span 标识 |
| `parent_span_id` | 父 span，构造请求→步骤树 |
| `step` | `tool` / `retrieve` / `model` / `handoff` 等 |
| `sampled` | 是否被采样 |
| `source` | `worker` / `sync` / `replay` |

`service_ai_events` 增加：

| 字段 | 用途 |
|---|---|
| `prompt_version` / `prompt_hash` | 定位 prompt 变更 |
| `model` | 模型标识 |
| `input_tokens` / `output_tokens` | 成本与质量分析 |
| `first_token_latency_ms` | 首 token 延迟 |
| `retry_count` | 重试次数 |

`service_audit_events` 不新增列；通过 `event_type` 扩展读访问事件。

### 7. 读访问审计

企业审计最常问的是“谁查看了这条记录”，当前只有写操作审计。新增：

- `CONVERSATION_VIEWED`：员工/客户打开详情页。
- `TRANSCRIPT_EXPORTED`：导出/下载（后续切片）。
- 不审计 3s 轮询：`GET .../messages?after_id=` 视为轮询，不产生审计。
- 同一 `actor + entity + action` 在 5 分钟窗口内去重，避免刷新/重复打开刷屏。
  当前去重是进程内窗口（单 worker 有效）；多 worker 部署需要后续换成共享存储。
- 元数据只放 `ip`、`user_agent`、`source`、`request_id`，不放消息正文。
- 读访问审计是 L2：写入失败返回 503，不静默成功。

### 8. 保留与清理

| 数据 | 热保留 | 归档/清理 |
|---|---|---|
| L2 审计 | 180 天起（可配 5–7 年） | 只追加；按保留期归档到 SIEM/WORM；应用不得行级改删 |
| L3 技术 trace | 30 天 | 异常/handoff 样本 1 年；聚合指标长期 |
| L3.5 AI 事件 | 普通 90 天；关键 1 年 | 关键事件不采样；普通按天归档 |
| L1 业务事实 | 按业务/合规 | 不在本 ADR 范围 |

清理任务每日运行，先 dry-run 计数，再按配置删除；审计清理必须单独审批并留清理审计。

### 9. 配置

```text
TRACE_SAMPLE_RATE=0.05
TRACE_BUFFER_SIZE=1000
TRACE_FLUSH_INTERVAL_MS=2000
TRACE_BATCH_SIZE=200
TRACE_RETENTION_DAYS=30
TRACE_ERROR_RETENTION_DAYS=365
AUDIT_RETENTION_DAYS=180
AI_EVENT_RETENTION_DAYS=90
AI_EVENT_CRITICAL_RETENTION_DAYS=365
VIEW_AUDIT_DEDUP_SECONDS=300
```

### 10. 指标与告警

- `trace_write_failures_total`
- `trace_dropped_total`
- `trace_buffer_utilization`
- `trace_flush_latency_ms`
- `audit_write_failures_total`
- `view_audit_dedup_total`

告警建议：`trace_dropped_total` 5 分钟 > 1%；`audit_write_failures_total` > 0；`trace_buffer_utilization` > 80%。

## 实施顺序与验收

| 步骤 | 内容 | 验收 |
|---|---|---|
| 1 | 拆 `AuditWriteError` / `TraceWriteError`；Trace 失败不 500，审计失败 503/500 | 故障注入：trace 写失败返回 200；审计写失败返回 503/500；业务回滚 |
| 2 | 采样 + 指标 + 结构化日志 | 异常/handoff 100%；正常按配置；指标可查；日志无 PII |
| 3 | 有界缓冲 + 批量异步写 | 队列满丢最旧并计数；关闭 flush；P95 不因 trace 写入上升 |
| 4 | `tool_executions` / `service_ai_events` 字段迁移 | 迁移可回滚；旧数据兼容；字段有测试 |
| 5 | 读访问审计 + 5 分钟去重 | 打开详情记一条；轮询不记；重复打开去重；审计失败 503 |
| 6 | 保留/清理任务 + OTel 兼容 | dry-run 计数；清理审计留存；`trace_id`/`span_id` 可映射 OTel |

## 后果

- 技术 trace 丢失不再影响客户业务；Trace 池满/写入慢只影响可观测性。
- 审计仍然失败关闭，但不再和 Trace 共用错误类型；审计可靠性可单独测试。
- 读访问审计会增加写入量，靠“只审计主动查看 + 5 分钟去重”控制。
- 需要新增迁移与配置；M1 先做步骤 1–2，步骤 3–6 按量排期。
- OTel 迁移不在 M1 强制；现有 UUID `trace_id` 保留，新增 `span_id` 不破坏旧查询。

## 拒绝的方案

- **全部 best-effort（含审计）**：丢审计证据，合规不可接受。
- **全部强一致（含 trace）**：Trace 抖动继续让业务 500。
- **只给 `TraceSinkError` 加 `try/except`**：会把审计失败一起吞掉；必须先拆失败源。
- **每 GET 都写读访问审计**：3s 轮询会淹没审计表；必须只审计主动查看并去重。
- **同步写 trace + 无采样**：成本与延迟随工具调用量线性上升。
- **M1 直接接 OTel**：字段与导出链路成本高，先保留兼容位。

## 实现记录

- 2026-11-19：步骤 1 完成——新增 `AuditWriteError` / `TraceWriteError`；`ToolGateway` 的 `sink.start/finish/reject` 改为 best-effort 并记结构化日志；`AuditWriteError` 映射 503；新增网关故障注入、HTTP 200 与审计 503 测试。
- 2026-11-19：步骤 2 完成——`SampledTraceSink` 尾采样（异常/关键工具 100%，正常成功默认 5%）；请求级 trace 中间件；进程内 `metrics` 计数器与 `/metrics` 文本端点，暴露 `trace_write_failures_total` 与 `trace_dropped_total`。`/metrics` 只含计数、无 PII，生产需在网络层限制访问。
- 2026-11-19：步骤 3 完成——`BufferedTraceSink` 有界队列（默认 1000）+ 后台批量写（2s/200 条），队列满丢最旧并计数，lifespan 关闭时 flush；`AsyncTraceSink` 由该实现取代。
- 2026-11-19：步骤 4 完成——迁移 `0012_trace_ai_fields`：`tool_executions` 增加 `span_id`/`parent_span_id`/`step`/`sampled`/`source`；`service_ai_events` 增加 `prompt_version`/`prompt_hash`/`model`/tokens/首 token 延迟/`retry_count`；模型返回与 AI 事件写入回填可用字段，schema 快照已重生成。
- 2026-11-19：步骤 5 完成——客户/坐席打开会话详情时写 `conversation.viewed` 审计；轮询消息不写；同一 actor/记录/动作 5 分钟进程内去重；`record_view` 独立事务，失败返回 503。
- 2026-11-19：步骤 6 完成——`retention.py` 与 `scripts/cleanup_observability.py`：默认 dry-run，`--apply` 删除过期 L3/L3.5；审计只报告、不删除（只追加触发器）；lifespan 每日清理任务。新增 OTel/W3C `telemetry.py`，请求中间件解析 `traceparent`，内部保持 UUID 并支持 32/16 hex 导出。
