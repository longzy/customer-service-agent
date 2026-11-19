# 企业智能客服的 Trace 与审计：行业实践调研

- 调研日期：2026-11-19
- 适用项目：企业级电商智能客服 Agent（M1 客户转人工闭环）
- 调研问题：企业真实场景里，智能客服的 “trace” 到底包含什么、保留多久、可靠性如何分层；这如何影响本项目 “Trace 写失败是否 500” 的决策。
- 调研方法：优先采用厂商官方文档、官方产品文档与监管机构问答；厂商博客/行业文章只用于补充实践细节。文中用【事实】标记可核对的一手来源，用【推断】标记本项目判断。
- 证据边界：本文能证明主流客服/可观测性产品如何划分 trace、审计与业务记录，不能直接证明某家企业的合规保留期一定适用于本项目；保留期与取证要求需法务/合规确认。

## 一、结论先行

1. **企业客服的 “trace” 不是一条日志，而是四层数据**：业务事实（会话/消息/录音）、审计轨迹（谁在何时访问/改动了哪条记录）、技术 trace（请求→轮次→步骤→模型/工具调用）、质量/分析事件（意图、置信度、转人工、质检结果）。四层的可靠性、保留期和采样策略不同。
2. **审计回答 “谁对哪条记录做了什么”，技术 trace 回答 “这次请求哪一步出了问题”**。前者要求完整、追加写、可长期取证；后者普遍采样、短期保留、允许丢失。把两者混成一个 `TraceSinkError` 是本项目当前矛盾的根源。
3. **AI 客服的技术 trace 有相对稳定的结构**：`interaction/session → turn → step → LLM call / tool call`，并把 handoff（转人工）作为一等事件，携带转人工原因、置信度、已执行动作和上下文包。
4. **技术 trace 的行业默认是 “异常全留、正常采样、异步落库、短期保留”**。公开实践常见 14–30 天保留；异常请求 100%，正常请求 3%–10% 起步。审计与业务记录则独立保留，且往往比技术 trace 长得多。
5. **对本项目：`tool_executions` 应定位为技术 trace，`service_audit_events` 是审计，`service_conversations/messages` 是业务事实，`service_ai_events` 是 AI 质量事件。** 技术 trace 写失败不应让业务 500；审计失败才应阻断或回滚。当前 `TraceSinkError` 同时承载两者，必须先拆失败源，再谈 best-effort。
6. **企业审计还有一个本项目未覆盖的缺口**：不仅记录“写了什么”，还要记录“谁查看/调阅/导出了哪条会话或录音”。这类读访问审计在客服行业是审计问题的核心。

## 二、四层数据模型

| 层 | 回答的问题 | 典型内容 | 可靠性 | 保留期 | 采样 |
|---|---|---|---|---|---|
| 业务事实 | 客户实际经历了什么 | 会话、消息、录音/转写、交接单、订单动作结果 | 强一致，失败回滚/5xx | 按行业；普通咨询 3–6 个月、投诉 2 年、金融 5–7 年 | 不采样 |
| 审计轨迹 | 谁在何时对哪条记录做了什么 | actor、action、timestamp、data touched、前后值、IP、来源 | 强一致、追加写、防篡改 | 独立于业务数据，通常更长（≥6 个月起） | 不采样 |
| 技术 trace | 这次请求哪一步慢/错/降级 | request/turn/step span、模型调用、工具调用、重试、延迟、错误码 | best-effort，可丢 | 14–30 天常见 | 异常 100%，正常按比例 |
| 质量/分析事件 | AI 表现如何、为什么转人工 | intent、confidence、handoff reason、质检分数、用户反馈 | 关键事件不丢，普通可聚合 | 聚合长期，原始样本按需 | 关键 100%，普通抽样 |

【事实】客服审计日志的四个必要字段是 actor、action、timestamp、data touched；审计条目必须追加写、可验证未被篡改，并导出到 SIEM；审计保留期应长于它所描述的录音/会话数据。参见 [SingleComm: Audit logs for contact centers](https://singlecomm.com/platform/guides/contact-center-audit-logs)。

【事实】Infobip 的 interaction log 用 `Interaction ID` 串联跨渠道、跨 handoff 的一次客户旅程；每行一个事件，字段包括事件名、状态、发生上下文、对象版本、执行者、客户 Person ID、Interaction ID、Conversation ID、时间戳和详情；日志只保留最近 14 天。参见 [Infobip: Interaction logs](https://www.infobip.com/docs/insights-and-analytics/logs/interaction-logs)。

【事实】Salesforce 的 Field History 保留 18 个月，记录字段变更的前后值、用户和时间戳，用于合规与取证。参见 [Salesforce: 項目履歴管理](https://help.salesforce.com/s/articleView?id=xcloud.shr_field_history_tracking.htm&type=5)。Zendesk 的 audit log 记录操作描述、时间、IP、actor/source 等。参见 [Zendesk: Audit logs](https://developer.zendesk.com/api-reference/ticketing/account-configuration/audit_logs.md)。

## 三、AI 客服技术 trace 的典型结构

### 3.1 分层

【事实】华为云一篇 LLM 可观测性实践把一次请求拆成三层，用同一个 `trace_id` 串联：

- **请求层**：渠道、用户标识、会话 ID、最终状态——回答“是谁出的事”。
- **步骤层**：检索、prompt 组装、模型调用、后处理——回答“哪一步出的事”。
- **调用层**：单次模型 API 的 token 数、首 token 延迟、总耗时、`finish_reason`、重试次数——回答“是不是模型本身的问题”。

该实践还给出取舍：异常请求原文 100% 保留、正常请求约 3% 采样；写入异步化；prompt 内容 hash 进 span；不要把应用日志再抄进 trace。参见 [华为云：LLM 可观测性该采的四类数据](https://bbs.huaweicloud.com/blogs/513079)。

【事实】Honeycomb 的 Agent Timeline 把 “一次会话” 组织成：conversation → 一个或多个 agent execution → 每次 execution 内的 LLM 调用、工具调用、handoff、重试、人工升级、下游服务 span。参见 [Honeycomb: Agent Timeline](https://www.honeycomb.io/blog/agent-timeline-flight-recorder-for-your-ai-agents)。

【事实】AWS Connect 要求 AI agent 的 server 对**每一轮**发布 `TRACING_SPAN` 事件，覆盖该轮的输入、输出和工具活动；CloudWatch 的 agent sessions 视图把同一会话/用户交互的 trace 分组，用于跨轮次排查。参见 [AWS Connect Administrator Guide](https://docs.aws.amazon.com/pdfs/connect/latest/adminguide/connect-ag.pdf)。

### 3.2 建议的最小字段

| 层 | 字段 |
|---|---|
| 请求 | `trace_id`、`interaction_id`/`conversation_id`、tenant、channel、customer 伪匿名 id、started_at、duration、final_status |
| 轮次 | `turn_id`、user_input_hash、intent、confidence、fallback/handoff 标记 |
| 步骤 | `span_id`/`parent_span_id`、step（retrieve/prompt/model/tool/handoff）、tool name、args_hash、result_status、error_code、latency_ms |
| 调用 | model、prompt_version/hash、input/output tokens、first_token_latency、finish_reason、retry_count |
| 转人工 | handoff_reason、trigger（confidence/policy/sentiment/customer_request/repeated_failure）、from_status/to_status、queue、wait_seconds、context_package 摘要 |
| 审计 | actor、action、timestamp、data_touched、before/after（配置类）、ip、source、request_id |

【事实】NICE 把转人工的上下文包定义为：身份与验证状态、意图与目标、会话摘要、已执行动作、情绪/紧迫性、建议下一步；转人工触发包括置信度不足、政策/风险、情绪、客户明确要求、复杂度、重复失败。参见 [NICE: AI-to-Human Handoff](https://www.nice.com/agentic-ai/ai-to-human-handoff-in-autonomous-service)。

【事实】OpenTelemetry 已发布 GenAI 语义约定，覆盖模型、token 用量、操作类型等标准属性；若要跨厂商/跨语言关联，trace 字段应优先对齐 OTel semconv，而不是自定义一套。参见 [OpenTelemetry GenAI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)。

## 四、保留期与合规边界

【事实】MiFID II Article 16(7) 要求相关记录保留 5 年，监管机构可要求延长至 7 年。参见 [ESMA Q&A](https://www.esma.europa.eu/print/pdf/node/204124)。

【事实】PCI DSS 禁止在交易授权后保存敏感认证数据（SAD），包括卡验证码；如果通话录音里留下了 CVV，也属于“保存”，即使录音加密也不豁免。参见 [BBSec: 通話録音とPCI DSS](https://www.bbsec.co.jp/tech-column/sc/20260715.html)。

【事实】国内客服录音管理的行业文章建议：普通咨询录音保存 3–6 个月、投诉纠纷 2 年、重大事件单独加密存储；并提到《网络安全法》要求网络日志留存不少于 6 个月。具体适用仍需法务确认。参见 [HollyCRM: 客服电话录音管理](https://www.hollycrm.com/innews/8057.html)。

【推断】对本项目：

- `service_conversations`/`service_messages` 是业务事实，不能因为 trace 写失败而回滚。
- `service_audit_events` 是审计，必须独立保留、追加写、不可改删；保留期应长于会话/录音数据。
- `tool_executions` 是技术 trace，保留 14–30 天足够；异常样本可长期归档。
- `service_ai_events` 是 AI 质量事件，转人工/失败/低置信必须保留，普通成功可聚合。

## 五、映射到本项目

| 本项目 | 应归属 | 当前问题 |
|---|---|---|
| `service_conversations` / `service_messages` | 业务事实 | 正常；不应被 trace 失败拖累 |
| `service_audit_events` | 审计 | 已追加写/触发器防改删；但工具路径的审计失败与 trace 失败共用 `TraceSinkError` |
| `tool_executions` | 技术 trace | 写失败 → `TraceSinkError` → 500；无采样、无异步、无丢失指标 |
| `service_ai_events` | AI 质量事件 | 有 intent/confidence/reply/failure；缺 prompt version/hash、token、首 token 延迟 |
| `trace_id` | 请求标识 | 目前是 UUID，无 span 父子关系、无 W3C traceparent；跨服务关联能力弱 |
| 审计覆盖 | 写操作 + 安全事件 | 登录、转人工、领取、接管、回复、关闭、转回、401/403/429 有审计；**查看/调阅/导出记录**没有审计 |

【事实】当前 `AsyncTraceSink._run()` 超时/异常抛 `TraceSinkError`（`backend/platform/observability.py:154-166`）；`ToolGateway` 不吞（`backend/tools/gateway.py:186`、`:323`）；全局异常处理器映射为 500（`backend/api/main.py:115-117`）。`ToolGateway._record()` 还会先调用 `self._audit(event)`（cancel gateway 的审计写入），失败同样转成 `TraceSinkError`。因此“Trace 失败”实际上混合了两种失败源。

## 六、综合建议

### 6.1 先拆职责，再谈降级

1. **拆异常类型**：`AuditWriteError`（审计，强一致）与 `ToolTraceError`（技术 trace，可降级）分开；不要让审计失败被 best-effort 吞掉。
2. **拆数据表**：`service_audit_events` 保持强一致、追加写、长期；`tool_executions` 改为技术 trace 表，允许采样/异步/短期。
3. **补读访问审计**：对“查看会话详情、查看交接单、导出/调阅”记录 actor/action/target/time；这是企业审计最常问的问题，不是可选项。

### 6.2 分级可靠性

| 级别 | 数据 | 写失败行为 |
|---|---|---|
| L1 | 业务事实（会话/消息/交接单状态） | 回滚 + 5xx |
| L2 | 审计（含读访问/导出） | 回滚 + 5xx/503；至少不能静默成功 |
| L3 | 技术 trace（tool_executions） | 记结构化日志 + 指标 + 采样；不影响业务 |
| L3.5 | AI 质量事件（转人工/失败/低置信） | 关键事件 100% 保留；普通成功可采样 |

### 6.3 技术 trace 的最小落地方案

- **写入**：本地 ring buffer + 后台批量写；进程崩溃可丢最后一批（可接受），用 `trace_write_failures_total` / `trace_dropped_total` 指标暴露。
- **采样**：异常/转人工/取消/失败 100%；正常查询 5%–10% 起步；采样决策在 trace 头，避免半条链。
- **保留**：热数据 14–30 天；异常样本长期归档；聚合指标长期。
- **字段**：至少补 `prompt_version/hash`、`first_token_latency`、`retry_count`、`handoff_reason`、`tool_args_hash`；`trace_id` 预留 OTel/W3C 兼容。
- **日志**：不要把日志正文抄进 trace；日志与 span 用 `trace_id` 关联。

### 6.4 需要产品/合规回答的问题

1. 技术 trace 丢失是否可接受？哪些事件必须 100% 保留（转人工、取消、失败、投诉）？
2. 审计是否要覆盖“查看/调阅/导出”，保留多久？是否要 SIEM/WORM？
3. 会话/录音保留期按普通咨询、投诉、重大事件如何分级？是否涉及金融/医疗/支付合规？
4. 采样率与存储成本上限；trace 丢失率超过多少要告警/阻断发布？
5. 是否在 M1 接 OTel/W3C trace context，还是先保留 UUID、M2 再迁移？

## 七、对本项目当前决策的直接回答

- **技术 trace 写失败不应该 500**：它是可观测数据，应 best-effort + 日志 + 指标 + 采样；业务成功不应因 trace 丢失而失败。
- **审计写失败不能 best-effort**：它承担“谁做了什么”的取证责任，失败应阻断/回滚；但前提是把审计从 `TraceSinkError` 中拆出来。
- **在本项目当前代码里，直接加 `try/except` 是错的**：`TraceSinkError` 同时可能来自 `tool_executions` 与 cancel 的审计写入，必须先拆失败源。
- **企业真实客服的 trace 不是“越全越好”**：异常全留、正常采样、审计独立、业务事实强一致，才是成本与合规都可接受的组合。

## 八、参考来源

- [SingleComm: Audit logs for contact centers](https://singlecomm.com/platform/guides/contact-center-audit-logs)
- [Infobip: Interaction logs](https://www.infobip.com/docs/insights-and-analytics/logs/interaction-logs)
- [Honeycomb: Agent Timeline](https://www.honeycomb.io/blog/agent-timeline-flight-recorder-for-your-ai-agents)
- [AWS Connect Administrator Guide（AI agent traces / TRACING_SPAN）](https://docs.aws.amazon.com/pdfs/connect/latest/adminguide/connect-ag.pdf)
- [华为云：LLM 可观测性该采的四类数据](https://bbs.huaweicloud.com/blogs/513079)
- [NICE: AI-to-Human Handoff](https://www.nice.com/agentic-ai/ai-to-human-handoff-in-autonomous-service)
- [OpenTelemetry GenAI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [ESMA: MiFID II Article 16(7) Q&A](https://www.esma.europa.eu/print/pdf/node/204124)
- [BBSec: 通話録音とPCI DSS](https://www.bbsec.co.jp/tech-column/sc/20260715.html)
- [HollyCRM: 客服电话录音管理](https://www.hollycrm.com/innews/8057.html)
- [Zendesk: Audit logs](https://developer.zendesk.com/api-reference/ticketing/account-configuration/audit_logs.md)
- [Salesforce: 項目履歴管理](https://help.salesforce.com/s/articleView?id=xcloud.shr_field_history_tracking.htm&type=5)
