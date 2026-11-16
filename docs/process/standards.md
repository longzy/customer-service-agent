# 工程标准（STD）

- 状态：已批准
- 批准：2026-11-16（本次会话由用户确认）
- 日期：2026-11-16
- 用法：评审、门禁、任务卡都引用 STD 编号，不重复描述规则
- 关系：[标准开发工作流](WORKFLOW.md) 定义流程；本文定义“什么算合格”
- 强制点图例：`已强制` = 已有脚本/CI 阻断；`待落地` = 规则已定，工具未接

## 1. 架构与依赖（STD-ARCH）

| ID | 规则 | 强制点 | 状态 |
|---|---|---|---|
| STD-ARCH-01 | 依赖方向单向：`api → agent_runtime → tools/workflows → domain/contracts`；下层不得 import 上层 | import-linter 或边界测试（每条 ADR 边界一个断言） | 待落地 |
| STD-ARCH-02 | Agent Runtime 不得直接访问数据库与业务系统，只能经 Tool | `tests/unit/test_package_boundaries.py` | 已强制 |
| STD-ARCH-03 | `packages/contracts` 是跨模块接口唯一定义源；不得在代码里另建同义模型 | 契约同步测试 | 部分 |
| STD-ARCH-04 | 新增模块必须同时有 lint、类型与至少一个测试入口 | `verify.sh` | 已强制 |
| STD-ARCH-05 | 违反架构不变量（`docs/architecture/invariants.md`）必须新增 ADR，不得静默放宽 | 评审 + ADR 目录 | 待落地 |

## 2. HTTP 与 API（STD-API）

| ID | 规则 | 强制点 | 状态 |
|---|---|---|---|
| STD-API-01 | 所有路由声明 `response_model`；返回类型不得是 `Any` | mypy + 契约测试 | 待落地 |
| STD-API-02 | 统一错误封套 `{code, retryable, visible, message}`；禁止同时存在 `{"detail"}` 与自定义 payload | 全局异常处理器 + 契约测试 | 待落地 |
| STD-API-03 | 对外路径统一 `/api/v1` 前缀；破坏性变更升版本，不原地改语义 | 路由测试 | 待落地 |
| STD-API-04 | 外部写接口必须接受 `Idempotency-Key` 头；服务端生成的随机键不能替代客户端幂等键 | API 测试 + DB 唯一约束 | 待落地 |
| STD-API-05 | 列表接口必须有 `limit`/`cursor`，并有上限；禁止无界返回 | 契约测试 | 待落地 |
| STD-API-06 | 状态码表：创建 201、删除 204、冲突 409、越权 404（不泄露存在性）、依赖失败 502/504 | API 测试 | 部分 |
| STD-API-07 | 所有外部输入有长度/格式上限；未知字段默认拒绝 | Tool Gateway + Pydantic strict | 部分 |

## 3. 数据与迁移（STD-DATA）

| ID | 规则 | 强制点 | 状态 |
|---|---|---|---|
| STD-DATA-01 | 金额用整数分，时间用 UTC ISO 8601 `Z`；禁止浮点金额与本地时间入库 | 契约测试 | 已强制 |
| STD-DATA-02 | 每个迁移必须可回滚（`downgrade` 有效），并在测试库演练 | `scripts/test-db.sh` + 迁移测试 | 部分 |
| STD-DATA-03 | 唯一约束、外键与 CHECK 必须同时存在于迁移与 ORM 模型；状态字段用 CHECK 或枚举表 | autogenerate 对比 + 迁移测试 | 待落地 |
| STD-DATA-04 | 事务边界只有一处：路由或仓储，不得两者都 commit | 评审 | 待落地 |
| STD-DATA-05 | 集成测试必须跑在独立测试库（`*_test`），禁止使用 `skipif` 静默跳过 | `scripts/test-db.sh` + CI 断言无 skip | 已强制 |
| STD-DATA-06 | 迁移遵循 expand → migrate → contract；不删列的同时改语义 | 评审 + 发布清单 | 待落地 |

## 4. 安全（STD-SEC）

| ID | 规则 | 强制点 | 状态 |
|---|---|---|---|
| STD-SEC-01 | 身份与租户只从认证上下文获取；请求正文出现身份字段即拒绝 | 中间件 + 测试 | 已强制 |
| STD-SEC-02 | Cookie 必须 `HttpOnly` + `SameSite=Lax` 起；非本机环境必须 `Secure` 且用 `__Host-` 前缀 | `tests/unit/test_csrf.py`（AC-21）；`__Host-` 前缀仍待落地 | 部分 |
| STD-SEC-03 | 写操作需要 CSRF 策略：SameSite + Origin 校验或双提交令牌 | `services/api/csrf.py` + `tests/unit/test_csrf.py`；双提交令牌仍待落地 | 部分 |
| STD-SEC-04 | 授权校验集中在统一 guard；禁止每个端点自行拼 `tenant_id + user_id` 条件 | 代码评审 + 覆盖测试 | 待落地 |
| STD-SEC-05 | 管理/调试端点独立鉴权，默认不挂载；环境开关不能作为唯一防线 | 路由测试 | 部分 |
| STD-SEC-06 | 仓库与 CI 必须有 secret scanning；密钥只存在于环境变量 | `scripts/check-secrets.py` 进 pre-commit 与 CI；gitleaks 与 push protection 待接入 | 部分 |
| STD-SEC-07 | 依赖审计与 SAST 无高危才可合并；许可证白名单校验 | CI（pip-audit/npm audit/CodeQL/许可证扫描） | 待落地 |
| STD-SEC-08 | 日志与审计不得包含密钥、令牌、完整支付信息与超范围个人信息 | 脱敏测试（AC-18） | 待落地 |

## 5. 前端（STD-FE）

| ID | 规则 | 强制点 | 状态 |
|---|---|---|---|
| STD-FE-01 | 前端类型由 OpenAPI/契约生成；禁止手写同义类型与 `as` 强转跳过校验 | 生成脚本 + lint | 待落地 |
| STD-FE-02 | CI 必须跑生产构建（`next build`）；构建失败不得合并 | CI | 待落地 |
| STD-FE-03 | 路由必须有错误边界；网络错误、空态、失败重试是必测状态 | 组件测试 | 部分 |
| STD-FE-04 | 单个组件 >200 行或 >3 个独立状态机时必须拆分 | 评审 + lint 规则 | 待落地 |
| STD-FE-05 | 可访问性：可聚焦、可键盘操作、有可读标签；关键流程有 a11y 断言 | axe/Testing Library | 待落地 |
| STD-FE-06 | 前端测试的 React `act()` 警告视为失败 | vitest 配置 | 待落地 |

## 6. 可观测与评测（STD-OBS）

| ID | 规则 | 强制点 | 状态 |
|---|---|---|---|
| STD-OBS-01 | 每个请求生成 `request_id`，经中间件贯穿日志、审计、响应头与 Tool 调用 | 中间件 + 测试（INV-13） | 待落地 |
| STD-OBS-02 | 结构化日志固定字段：`request_id`、`tenant_id`、`tool`、`state`、`error_code`；禁止字符串拼接 | 日志格式测试 | 待落地 |
| STD-OBS-03 | 关键状态迁移写审计记录；审计失败按失败关闭处理 | Gateway 测试 | 部分 |
| STD-OBS-04 | 模型/Prompt/Tool 变更必须运行封存评测集并记录通过率（INV-16） | CI + `evals/` | 待落地 |
| STD-OBS-05 | 核心链路定义 SLO（可用性、P95、错误率），有指标与告警 | 监控配置 | 待落地 |

## 7. 测试（STD-TEST）

| ID | 规则 | 强制点 | 状态 |
|---|---|---|---|
| STD-TEST-01 | 测试只从公共 seam 观察行为；新增 seam 必须在卡里声明 | `docs/process/review.md` 六问 | 部分 |
| STD-TEST-02 | 测试名用中文描述行为并内嵌 `_AC_XX`；一个测试只追溯一个 AC | `tests/unit/test_naming_convention.py` | 已强制 |
| STD-TEST-03 | 禁止只测 happy path；失败矩阵的每格必须有测试或不适用理由 | 卡 2.4 + 评审 | 部分 |
| STD-TEST-04 | 新增/修改代码的 diff 覆盖率 ≥70%，核心模块 ≥80% | CI | 待落地 |
| STD-TEST-05 | 关键模块突变分数：Workflow/Tool Gateway ≥80%，Policy/领域映射 ≥70% | `scripts/mutation.sh`（夜间） | 部分 |
| STD-TEST-06 | 禁止 `sleep` 等待；异步测试用事件与超时断言 | 评审 + lint | 待落地 |
| STD-TEST-07 | flaky 测试 24 小时内修复或隔离，隔离需登记原因与 owner | CI 报告 | 待落地 |
| STD-TEST-08 | 跨服务边界用消费者驱动契约测试，不用大量 E2E 代替 | Pact 或契约夹具 | 待落地 |

## 8. Git 与协作（STD-GIT）

| ID | 规则 | 强制点 | 状态 |
|---|---|---|---|
| STD-GIT-01 | 提交遵循 Conventional Commits；`type(scope): 中文描述`，scope 用任务号或模块 | commitlint / CI | 待落地 |
| STD-GIT-02 | `main` 受保护：禁止直推，必须 PR + 1 次评审 + required checks | 分支保护 | 待落地 |
| STD-GIT-03 | 分支短命（≤3 个活跃），命名 `feat/T-XX-slug`、`fix/T-XX-slug` | 评审 | 待落地 |
| STD-GIT-04 | PR 描述固定四段：动机、变更、验证、风险 | PR 模板 | 已落地（模板） |
| STD-GIT-05 | 禁止 `--no-verify` 直推；紧急绕过需在 PR 写明并在 24h 内补跑 | 审计 + 评审 | 待落地 |
| STD-GIT-06 | 评审者不得是实现者；AI 实现必须由另一上下文评审 | 评审记录 | 已强制（流程） |
| STD-GIT-07 | 依赖升级单独提交并附回归结果 | 评审 | 待落地 |

## 9. 发布与供应链（STD-REL）

| ID | 规则 | 强制点 | 状态 |
|---|---|---|---|
| STD-REL-01 | 版本遵循 SemVer；`feat` → MINOR、`fix` → PATCH、`BREAKING CHANGE` → MAJOR | CI + 发布脚本 | 待落地 |
| STD-REL-02 | CHANGELOG 由提交生成草稿，人工润色；对外版本用 Keep a Changelog 结构 | 发布流程 | 待落地 |
| STD-REL-03 | 发布必须附迁移说明与回滚步骤；迁移先在测试库演练 | 发布清单 | 待落地 |
| STD-REL-04 | 产出 SBOM 并签名；构建可复现 | CI（CycloneDX + Sigstore） | 待落地 |
| STD-REL-05 | 许可证清单与政策检查（禁止未批准许可证进入依赖） | CI | 待落地 |

## 10. AI 协作（STD-AI）

| ID | 规则 | 强制点 | 状态 |
|---|---|---|---|
| STD-AI-01 | Agent 开工先恢复状态并复述五项；结束前更新事实源 | `AGENTS.md` + `check-status.py` | 已强制 |
| STD-AI-02 | 实现者不得自审；评审必须由独立上下文完成 | `check-docs.py`（存在性）+ 流程 | 部分 |
| STD-AI-03 | AI 生成的依赖必须验证存在性与许可证；禁止凭记忆引入包 | CI + 评审 | 待落地 |
| STD-AI-04 | AI 生成的测试必须通过反向验证与突变抽查，禁止断言复算实现 | 卡 4 + `mutation.sh` | 部分 |
| STD-AI-05 | 模型/Prompt 变更必须跑封存评测并记录版本 | CI + `evals/` | 待落地 |
| STD-AI-06 | Agent 不得修改不变量语义、跳过门禁、编造 AC 或证据 | 评审 + 审计 | 部分 |
| STD-AI-07 | 上下文预算：入口 ≤60 行、状态 ≤80 行、单份 process ≤300 行、卡 ≤120 行 | `check-docs.py` | 待落地 |

## 11. 文档治理（STD-DOC）

| ID | 规则 | 强制点 | 状态 |
|---|---|---|---|
| STD-DOC-01 | 同一事实只有一个写入位置；其余为派生视图 | `check-status.py` | 已强制 |
| STD-DOC-02 | 所有内部链接与反引号路径必须可解析（含 `tasks.md` 与已完成卡） | `check-docs.py` 扩展 | 部分 |
| STD-DOC-03 | 状态词表只有一份；检查器与规范共用同一常量 | `check_status_vocabulary_sync` | 部分 |
| STD-DOC-04 | 状态类文档不得手工维护历史过程；只保留当前事实与决策 | `check-status.py` | 已强制 |
| STD-DOC-05 | 已归档文档（handoff、历史评审）必须标注“已被取代”与替代链接 | 评审 | 待落地 |

## 12. 采用顺序

1. **第 1 周**：STD-GIT-02/04/05、STD-DATA-05、STD-API-01/02、STD-OBS-01、STD-FE-02、STD-DOC-01/02。
2. **第 2 周**：STD-SEC-01/02/03/06/07、STD-ARCH-01、STD-TEST-04。
3. **第 3 周**：STD-API-03/04/05、STD-DATA-03/04、STD-FE-01/04/05、STD-AI-03/05。
4. **第 4 周**：STD-OBS-02/04/05、STD-REL-01/02/04/05、STD-TEST-07/08。

每条规则落地时必须同时登记“强制点”；没有强制点的规则降级为建议（见 WORKFLOW 第 11 节）。
