# 开发规范评审：与主流工程实践的差距

- 状态：已完成
- 日期：2026-11-16
- 评审范围：`AGENTS.md`、`CLAUDE.md`、`GEMINI.md`、`docs/process/**`、`docs/specs/001-order-cancel/**`、`docs/tasks/**`、`docs/reviews/**`、`docs/architecture/**`、`docs/adr/**`、`scripts/**`、`.githooks/**`、`backend/**`、`apps/web/**`、`pyproject.toml`
- 方法：全量阅读 + 运行 `./scripts/verify.sh`、`pytest`、`scripts/check-docs.py`、`scripts/check-route-coverage.py`、`scripts/mutation.sh --self-test`；两个独立子上下文分别做代码/安全审计与文档/门禁审计；联网核对主流一手资料（见第 10 节）
- 限制：未验证 GitHub 仓库的服务端分支保护与 CI 配置（本机无网络访问凭据）；未在第二台机器复现环境

## 0. 结论先行

**这套规范的“设计”处在主流 SDD（Spec-Driven Development）的第一梯队，但“强制力”和“覆盖面”只到入门水平。**

- 设计强：一个变更一个目录、EARS 需求、AC 编号贯穿、执行卡、独立评审、不变量清单——这些结构与 GitHub Spec Kit、AWS Kiro 同构，部分做法（执行卡、评审留痕门禁、垂直切片规则）比两者更严谨。
- 执行弱：全部机器规则都在本地 git hook 里，`git push --no-verify` 一条命令即可绕过；没有服务端 CI，也没有分支保护；证据是“粘贴的命令输出”，不是可复现的构建产物。
- 覆盖窄：API 契约、安全基线、数据隔离、前端架构、发布与版本、可观测与评测七类基础规范缺失；不变量 INV-13/INV-16 宣称有强制点，实际没有实现。
- 状态腐烂：`STATUS.md` 与 `tasks.md` 已经互相矛盾（本次评审已修复，见第 6 节），说明“手工维护多份状态副本”在设计上不可持续。

三个最优先动作：

1. 建服务端 CI 与 required checks，把本地 hook 降级为快速反馈（P0-1）。
2. 把状态改为派生视图，用脚本校验 `STATUS.md ↔ tasks.md ↔ 执行卡`（P0-2，本次已落地 `scripts/check-status.py`）。
3. 集成测试改用独立测试库并禁止静默 skip，同时补 API/安全两类规范（P0-3、P1-1、P1-2）。

## 1. 评分卡

评分口径：0 = 完全没有；1 = 只写在文档里；2 = 有约定但靠自觉；3 = 部分机器强制；4 = 主流水平且强制；5 = 超出主流。

| 维度 | 得分 | 判定 | 关键依据 |
|---|---|---|---|
| AI 入口与上下文治理 | 4.5 | 领先 | `AGENTS.md` 分层权威顺序、指针式适配文件、五项恢复摘要；主流 AGENTS.md 约定已对齐 |
| 规格驱动（SDD） | 4.0 | 领先 | `docs/process/sdd.md` 固定路径与门禁、EARS、AC 追溯、设计卡 4.1 人类决策 |
| 测试策略与 TDD | 3.0 | 对齐设计，执行打折 | seam 表、红-绿证据、突变阈值都已写；突变未进任何门禁，测试库未隔离 |
| 追溯链 | 2.5 | 部分 | 18/20 条 AC 有测试名引用；AC-17/18 空转；评审记录不做逐 AC 判定 |
| 门禁与 CI | 1.0 | 落后 | 无 `.github/`、无 CI、无 required checks；`--no-verify` 可整体绕过 |
| 静态检查基线 | 2.5 | 部分 | ruff + mypy strict 已强制；缺 `S/BLE/ASYNC`，前端无 build 门禁 |
| API 与数据契约 | 1.5 | 落后 | 无 `response_model`、双错误格式、无 `/api/v1`、无 `Idempotency-Key` 入口、无分页规范 |
| 安全与供应链 | 1.0 | 落后 | 无 secret/SAST/依赖审计；Cookie 无 `Secure` 且被测试固化；无 CSRF |
| 可观测与评测 | 0.5 | 宣称未落地 | `trace_id` 非请求级、审计是空函数、`evals/` 空目录、无 OTel 依赖 |
| 状态与文档治理 | 1.5 | 落后 | 手写多副本状态；检查器只验“存在”不验“为真”；文档 6185 行 vs 代码 7924 行 |
| 发布与协作 | 1.0 | 缺失 | 无 PR 模板、CODEOWNERS、CHANGELOG、版本策略、分支策略 |
| **综合** | **2.1 / 5** | 设计 4.5，强制力 1.5，覆盖面 1.7 | — |

> 综合分低不代表项目差：这个仓库的**文档与流程设计质量**明显高于同规模项目；低分集中在“没被机器守住”和“没写规范”的部分。

## 2. 与主流的对齐矩阵

| 主题 | 主流基线 | 本仓库 | 判定 |
|---|---|---|---|
| Agent 入口 | `AGENTS.md` 开放格式（60k+ 项目采用，Linux Foundation 托管），就近文件优先，单文件 <200 行 | 有 `AGENTS.md` + 两个指针文件；但规则仍分散在 5 处，无嵌套文件，无上下文预算 | 对齐偏领先 |
| 规格驱动 | Spec Kit 五段（specify/plan/tasks/implement/converge）；Kiro 三件套 + EARS + hooks/steering | 固定路径、三件套 + 执行卡 + 评审记录；用 git hook 代替工具 hooks | 对齐偏领先 |
| 需求语法 | EARS 五类句式（Mavin 2009），可测试可追溯 | `requirements.md` 已用 EARS，并有元测试校验句式 | 对齐 |
| 追溯 | 轻量做法：AC ID 进测试名；受监管场景才要双向 RTM | 测试名带 `_AC_XX`，但无矩阵生成、无缺口门禁 | 部分 |
| 测试形状 | 测试奖杯/金字塔按风险配比；关键旅程 E2E；契约测试跨服务 | 300 单测 + 集成、35 前端测试；无 E2E、无契约测试、无覆盖率数据 | 部分 |
| 突变测试 | 只跑核心模块，Stryker 默认 high 80 / low 60，不默认阻断 | 有规范与脚本，但范围配置过宽、阈值不进任何门禁 | 有规范无强制 |
| CI/分支 | DORA：trunk-based（活跃分支 ≤3、每天合并）；服务端 required checks 是唯一硬门禁 | `main` 直推，108 次提交；本地 hook 是唯一门禁 | 落后（最大短板） |
| 提交与发布 | Conventional Commits 1.0.0 + SemVer；semantic-release/Changesets；Keep a Changelog | 提交信息事实上符合 Conventional Commits，但规范未落文；无版本与 CHANGELOG | 有习惯无规范 |
| 代码质量 | ruff/ESLint、mypy/pyright strict、Sonar 新代码门禁、CodeQL、gitleaks、Dependabot、SBOM | ruff + mypy strict + ESLint/Prettier；其余全无 | 部分 |
| API 契约 | OpenAPI 作为唯一源，前端类型生成；统一错误封套；版本前缀；`Idempotency-Key` | 5 个 Tool 有 JSON Schema；HTTP 层无 `response_model`、错误双轨、无版本 | 落后 |
| 安全 | OWASP ASVS/LLM Top 10；secret scanning + push protection；SAST；依赖审计 | 身份不取自正文、资格确定性这两条硬约束有实现；其余安全基线缺失 | 落后 |
| 治理文件 | README/CONTRIBUTING/SECURITY/CODE_OF_CONDUCT/LICENSE/CODEOWNERS + .editorconfig/.gitattributes + PR/issue 模板 | 只有 README；缺 8 项 | 缺失 |
| 状态文档 | docs-as-code + 单一事实源；STATUS.md 类文件必须自动生成 | 手写 `STATUS.md`，与 `tasks.md` 已矛盾 | 落后 |
| AI 代码治理 | 幻觉依赖检查（USENIX 2025：商用模型 5.2%、开源 21.7% 的包名不存在）、许可证、测试自证、人工评审 | 有“实现者不得自审”“证据留痕”；无依赖存在性、许可证、eval 门禁 | 部分 |

## 3. 关键差距

### P0-1 没有服务端门禁，所有规则都可一条命令绕过

- 现状：`.githooks/pre-commit` 与 `pre-push` 是唯一强制点；`pre-push` 注释直接写明可用 `git push --no-verify` 绕过（`.githooks/pre-push:3`）；仓库无 `.github/`，无 CI，无分支保护。
- 证据：`ls .github` 不存在；`git config core.hooksPath` 只在本机生效，新 clone 不继承。
- 影响：任何一次“急一下”的推送都会跳过全部检查，而事后没有任何记录能发现；门禁强度等于开发者自觉。
- 主流：服务端 required status checks 是唯一硬门禁，本地 hook 只做反馈加速；绕过 `--no-verify` 靠审计而不是技术封堵。
- 最小修复：加 CI 跑 `./scripts/verify.sh --no-record`，把 lint/type/test/docs 设为 required check；`--no-verify` 需在 PR 描述中写明原因。

### P0-2 状态事实源已经腐烂，且检查器只验“写了没有”

- 现状（评审时）：`docs/STATUS.md` 写“尚无订单查询与取消逻辑”，但查询、取消、转人工均已实现；`进行中` 的 14 条里 9 条以“已完成”开头；`下一步` 让从 T-10/T-05/T-02 开始，三者早已完成；有序列表编号为 `1,2,2,3,3,4`；T-11、T-12、T-13 三个未完成任务从未出现在状态页。
- 证据：`scripts/check-docs.py:118-122` 只检查字段名是否存在；`check_verification_block()` 只要求块里出现 `passed`。
- 影响：交接与恢复流程的前提（“仓库是事实源”）不成立；Agent 读到的状态是错的，比没有状态更危险。
- 主流：状态类文档要么自动生成，要么交给 Issue/Project 单一事实源；`STATUS.md` 手写多副本是公认的失效模式。
- 已落地修复（本次）：`scripts/check-status.py` 校验 `STATUS.md ↔ tasks.md ↔ 执行卡` 三方一致、未完成任务不得消失、列表编号连续；`STATUS.md` 已按事实重写；`verify.sh` 已接入该检查。

### P0-3 验证脚本不闭合：非 hermetic、重复执行、集成测试可能假绿

- 现状：
  - `scripts/verify.sh` 的 `prod import` 与“记录验证结果”两步漏了 `UV_CACHE_DIR`，在受限环境直接报 `Failed to initialize cache`（本次复现）；
  - pytest/mypy/check-docs 各跑两遍，20 秒里约一半是重复工作；
  - 集成测试直连开发库 `customer_service`（`tests/integration/db_utils.py:10`），且数据库不可用时 `skipif` 静默跳过（`tests/integration/test_cancellation_repository.py:21`）——在无数据库环境里，`verify.sh` 会显示“全绿”但集成覆盖为 0。
- 影响：门禁结论不可信；测试可能污染开发者库；新机器上“通过”不等于“验证过”。
- 主流：CI 用 ephemeral 数据库服务；测试库与开发库分离；skip 必须有显式配额并在 CI 里可见。
- 已落地修复（本次）：新增 `scripts/test-db.sh`（建库 → `alembic upgrade head` → pytest），`verify.sh` 改用它并把结果只跑一次；`verify.sh` 增加 `--no-record` 供 CI 使用。

### P0-4 安全基线缺失，且缺陷被写进了测试预期

- 现状：
  - 会话 Cookie 只设 `httponly`、`samesite=lax`，没有 `secure`（`backend/api/session_routes.py:49-55`）；`tests/unit/test_session.py:31` 断言 `"secure" not in cookie`，把缺陷固化为预期；
  - 无 CSRF token/Origin 校验，写操作仅靠 SameSite=Lax 兜底；
  - 无 secret scanning；工作区 `.env` 内有真实模型密钥（未入库，但无任何扫描能阻止下次误提交）；
  - 管理端点 `/_admin/faults` 仅靠环境开关挂载，无独立鉴权。
- 影响：任何一次误配置都会把开发期身份模型带上线；安全回归无法被发现。
- 主流：Cookie 基线（`Secure`+`HttpOnly`+`SameSite`+`__Host-`）、CSRF 策略、secret scanning + push protection、SAST、管理面独立鉴权。
- 最小修复：Cookie 按环境补 `secure`；加 `gitleaks` 与依赖审计到 CI；写 `SECURITY.md` 与安全基线标准（见 `docs/process/standards.md`）。

### P0-5 无 CI 导致“AI 一次改很多、无人复核”的风险没有兜底

- 现状：108 次提交里，一个任务常常拆成 `feat` + 多个 `fix` + `docs` 五次提交（如 T-08 四轮评审对应 6 次提交），但没有一次服务端构建；AI 生成的代码只在本地被验证。
- 影响：环境差异、锁文件漂移、Node/Python 版本差异都无法被发现。
- 最小修复：CI 固定 Python/Node 版本，`uv sync --frozen` + `pnpm install --frozen-lockfile`，与本地同一脚本。

### P1-1 API 契约不可作为契约消费

- 现状：路由没有 `response_model`，返回 `Any`（`backend/api/cancellation_routes.py:68`）；业务错误用 FastAPI 默认 `{"detail"}`，网关错误用 `{code,retryable,visible,message}`，同一 API 两套错误格式；无 `/api/v1` 前缀；外部写接口不收 `Idempotency-Key`，幂等键由服务端 `uuid4()` 生成（`backend/api/cancellation_routes.py:70`）。
- 影响：AC-09（重复提交只产生一条申请）只在 OMS 侧成立，客户端重试必然新建任务；前端只能手写类型（`apps/web/components/ConfirmCard.tsx:9`）。
- 主流：OpenAPI 为唯一源 + 生成前端类型；统一 ErrorEnvelope；版本前缀；幂等键走 header。
- 修复：见 `docs/process/standards.md` 的 STD-API-01..05。

### P1-2 分层出现环，边界测试只覆盖一条约束

- 现状：`backend/tools/gateway.py:14` import `backend.api.auth`，`backend/workflows/cancel.py:15` import `backend/api.models`，而 `backend/api/main.py` 又 import tools/workflows，形成 `api → workflows → tools → api` 闭环；`tests/unit/test_package_boundaries.py:6` 只禁止 `agent_runtime` import `mock_oms`/SQLAlchemy，ADR-0004 的四条边界只覆盖一条。
- 主流：import-linter/依赖方向矩阵，每条架构约束对应一个可执行断言。
- 修复：把 ADR 边界逐条映射为测试（STD-ARCH-01）。

### P1-3 前端没有生产构建门禁

- 现状：`verify.sh` 只跑 lint/format/typecheck/test，不跑 `next build`（`apps/web/package.json:7` 的 `build` 无人调用）；无 `error.tsx`；单组件 `ChatShell.tsx` 332 行承载 6 个 `useState` 的状态机；测试输出 8 处 React `act()` 警告无人拦截。
- 主流：CI 必跑生产构建；错误边界与状态机分层；前端警告纳入门禁。
- 修复：CI 加 `pnpm build`；act 警告升级为失败或至少告警（STD-FE-02）。

### P1-4 突变检查名不副实

- 现状：`pyproject.toml` 的 `source_paths = ["backend"]` 让 `mutmut` 变异全部服务代码，而 `tdd.md` 第 5 节声称“只跑 workflows/tools/api.domain”；`scripts/mutation.sh` 只是对全量结果做过滤；阈值只写在文档里，脚本不阻断。
- 已落地修复（本次）：`source_paths` 收敛为三个核心目录；`mutation.sh` 增加阈值判定、`--report` 与 `--self-test`，阈值 80/80/70 与 `tdd.md` 一致。
- 剩余：突变尚未进入夜间流水线（应进 G3，不进 pre-commit）。

### P1-5 可观测与评测“有文档、无实现”

- 现状：INV-13 要求“每次模型、Tool 调用与状态转换可关联到同一链路”，但 `trace_id` 由每个 handler 各自 `uuid4()`（`backend/api/cancellation_routes.py:70`），不进日志、不进响应头；`ToolGateway` 默认审计是空函数（`backend/tools/gateway.py:105`）；`evals/README.md` 仍指向不存在的 `docs/specs/M1/.../acceptance.md`；`pyproject.toml` 无 OpenTelemetry 依赖。
- 主流：request-id 中间件 + 结构化日志字段集 + trace 导出 + 封存评测集；模型/Prompt 变更必须跑 eval。
- 修复：T-12 落地 trace_id 与脱敏日志；T-13 落地评测；INV-13/16 各自绑定一个测试或脚本（STD-OBS-01/02）。

### P1-6 规范覆盖缺七类，且规则有多份副本

- 缺失：API 设计、安全基线、数据与迁移、前端架构、发布与版本、可观测、AI 生成代码专项。
- 重复：状态词 3 份（检查器 14 词、`process/README.md` 8 词、`sdd.md` 9 词）；启动读取顺序 5 处；门禁分级 4 处；路径布局 4 处。
- 影响：改一处规则要同步 N 处，AI 与人都无法判断哪份是最新。
- 修复：`docs/process/standards.md` 用 STD ID 收敛规则并标注唯一强制点；`docs/process/WORKFLOW.md` 收敛流程。

### P2 其余问题

- `sdd.md:88` 把 `已确认` 列为执行卡状态，但 `check-docs.py` 的白名单没有该词，卡一旦写 `已确认` 会直接失败；检查器里又专门 `-= {"已确认"}` 掩盖了这个矛盾。
- 评审记录只检查是否含“结论”二字（`scripts/check-docs.py:231`），写“结论：不通过”也能通过；16 份评审没有一份逐 AC 给结论。
- 任务卡大小规则（≤2 AC）只对未完成卡告警，已完成的 T-08 绑了 8 个 AC。
- 仓库卫生文件缺 8 项（CONTRIBUTING/SECURITY/CODE_OF_CONDUCT/LICENSE/CODEOWNERS/.editorconfig/.gitattributes/PR 与 issue 模板）。
- `README.md:86` 说“仓库已设置 core.hooksPath”，但该配置只在本机 `.git/config`，新 clone 需要重新执行，文档没有给出命令。

## 4. 门禁的真实边界

| 可以机器保证 | 通道 |
|---|---|
| 19 条内部链接可解析、状态词在白名单、`STATUS.md` 字段齐全 | `check-docs.py` |
| 规格目录命名、必需文件、AC 在 `tasks.md` 被引用 | `check-docs.py` |
| 已完成卡有评审文件且文件含“结论”二字 | `check-docs.py` |
| 已完成卡引用的仓库路径存在 | `check-docs.py` |
| 10 条路由字面量被测试提及（任何提及都算，包括注释） | `check-route-coverage.py` |
| 格式、lint、类型、测试、前端四件套 | `verify.sh` |

| 不能机器保证（靠自觉） | 后果 |
|---|---|
| `STATUS.md` 的叙述为真 | 状态早已腐烂（现已加 `check-status.py`） |
| 评审由独立上下文完成 | 可自审自签 |
| 评审结论为“通过” | 写“不通过”也能过 |
| 证据是真实运行输出 | 粘贴任意 `passed` 文本即可 |
| 突变分数达标 | 阈值只写在卡里 |
| 设计卡绑定 ≤2 AC | 仅警告，且跳过已完成卡 |
| 不变量 INV-13/16 被实现 | 无任何测试或脚本 |
| hook 已安装、未被 `--no-verify` 绕过 | 无记录 |

结论：当前门禁保证的是“文档长得合规”，不是“状态为真、测试有效”。

## 5. 流程成本

| 指标 | 数值 |
|---|---|
| 文档总行数 | 6185 行（评审时） |
| 代码行数 | Python 6129 + Web 1795 = 7924 行 |
| 文档/代码比 | 0.78 : 1 |
| 每个完成任务的平均产出 | 执行卡 116 行 + 评审 38 行 + `STATUS.md`/`tasks.md` 若干条 |
| 状态副本 | 每个任务 4 处（`tasks.md` 勾选、卡状态、评审结论、`STATUS.md` 叙述） |
| `verify.sh` 重复执行 | pytest/mypy/docs 各 2 次（已修） |

成本本身不是问题——**问题在于成本换来的证据不可信**。规范越重，越需要机器保证，否则“写了很多文档”会掩盖“没有验证”。

## 6. 事实漂移清单（评审时发现，本次已修复部分）

| 位置 | 声称 | 实际 |
|---|---|---|
| `docs/STATUS.md:6`（原） | 尚无订单查询与取消逻辑 | 查询、取消、转人工、登录均已实现 |
| `docs/STATUS.md:62-77`（原） | “进行中”14 条 | 9 条以“已完成”开头；T-09/T-10 一处写“尚未开始”一处写“已完成” |
| `docs/STATUS.md:85-90`（原） | 下一步从 T-10/T-05/T-02 开始 | 三者均已完成；列表编号 1,2,2,3,3,4 |
| `docs/STATUS.md`（原） | 未提及剩余任务 | T-11、T-12、T-13 在 `tasks.md` 仍未勾选，状态页不可见 |
| `docs/specs/001-order-cancel/tasks.md:30` | T04 产出 `backend/api/middleware.py` | 文件不存在，实际为 `auth.py`（已修） |
| `docs/tasks/001-order-cancel/T-02.md:110` | 76 passed | 评审记录写 82 passed；卡内证据未回填（历史证据不改写，作为“记录漂移”案例保留） |
| `docs/tasks/001-order-cancel/T-19.md:120` | 两轮评审 | 评审记录为三轮；卡内结论已改为三轮（已修） |
| `evals/README.md:5` | `docs/specs/M1/001-order-cancel/acceptance.md`、AC-01~19 | 路径不存在；实际是 `requirements.md`、20 条 AC（已修正路径与数量） |
| `docs/adr/0004-engineering-baseline.md:25` | OTel 在 T-12 接入 | 仓库无 OTel 依赖，T-12 未开工 |
| `docs/handoffs/2026-11-14-foundation.md` | 等待评审/代码未开始/`docs/specs/M1/...` | 全部过期；handoff 未标注“已被取代” |

机制性结论：**同一事实有 4 份手写副本时，漂移是必然而不是疏忽**。修复方向不是“下次更仔细”，而是“只留一个可校验的事实源”。

## 7. 建议的演进路线

| 阶段 | 目标 | 对应交付 |
|---|---|---|
| 第 1 周 | 让门禁可信 | CI + required checks；`verify.sh` 闭合；测试库隔离；`check-status.py`、`trace.py` 进 CI |
| 第 2 周 | 让规范完整 | `docs/process/WORKFLOW.md` 分级流程；`docs/process/standards.md` 的 API/安全/数据/前端规范 |
| 第 3 周 | 让状态自动 | 由 `tasks.md` + 卡 front-matter 生成 `STATUS.md`；文档链接与路径全量校验 |
| 第 4 周 | 让质量可度量 | 覆盖率（新代码 diff）、突变（夜间）、flaky 检测、DORA 四项指标 |
| 持续 | 防膨胀 | 每条规则有 owner 与强制点；每季度删一条无效规则 |

详见 [标准开发工作流](../process/WORKFLOW.md) 与 [工程标准](../process/standards.md)（均为草案，待批准）。

## 8. 复现命令

```bash
./scripts/verify.sh --no-record      # 完整验证（不写回状态文件）
./scripts/test-db.sh -q              # 独立测试库：建库 → 迁移 → 测试
python3 scripts/check-status.py      # 状态三方一致
python3 scripts/trace.py --strict    # AC 追溯矩阵
python3 scripts/check-docs.py        # 文档结构与链接
./scripts/mutation.sh --self-test    # 突变阈值逻辑自检
git config --get core.hooksPath      # 本机 hook 是否安装
```

## 9. 主流资料（访问于 2026-11-16）

- [AGENTS.md 开放格式](https://agents.md/)（60k+ 项目，Agentic AI Foundation 托管）
- [Claude Code 记忆与规则](https://code.claude.com/docs/en/memory)
- [GitHub Spec Kit 快速开始](https://github.github.io/spec-kit/quickstart.html)
- [AWS Kiro Specs](https://kiro.dev/docs/specs/) 与 [EARS 原始出处](https://alistairmavin.com/ears/)
- [DORA：trunk-based development](https://dora.dev/capabilities/trunk-based-development/)
- [GitHub 受保护分支](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/) 与 [Semantic Versioning 2.0.0](https://semver.org/)
- [StrykerJS 配置（high 80 / low 60）](https://stryker-mutator.io/docs/stryker-js/configuration/)
- [SonarQube 质量门禁（新代码覆盖率 80%）](https://docs.sonarsource.com/sonarqube-server/2025.1/instance-administration/analysis-functions/quality-gates)
- [gitleaks](https://github.com/gitleaks/gitleaks)、[CodeQL](https://docs.github.com/en/code-security/code-scanning/introduction-to-code-scanning/about-code-scanning-with-codeql)、[SLSA](https://slsa.dev/spec/v1.0/levels)
- [OWASP LLM Top 10](https://genai.owasp.org/llm-top-10/)、[NIST AI RMF](https://www.nist.gov/itl/ai-risk-management-framework)
- [USENIX Security 2025：幻觉依赖包](https://www.usenix.org/conference/usenixsecurity25/presentation/spracklen)
- [Write the Docs：docs as code](https://www.writethedocs.org/guide/docs-as-code/)
