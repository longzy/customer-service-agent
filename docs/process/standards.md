# 工程标准（STD）

- 状态：已批准
- 批准：2026-11-16（同日收缩为“只保留可强制执行”的规则）
- 判断标准：**没有强制点的不是标准，是建议**。未落地的缺口见[评审报告](../reviews/2026-11-16-dev-standards-review.md) 第 3 节，不在此维护。

| ID | 规则 | 强制点 |
|---|---|---|
| STD-ARCH-02 | Agent Runtime 不直接访问数据库或业务系统，只经 Tool | `tests/unit/test_package_boundaries.py` |
| STD-ARCH-04 | 新模块必须有 lint、类型与至少一个测试入口 | `scripts/verify.sh` |
| STD-DATA-01 | 金额用整数分，时间用 UTC ISO 8601 `Z` | 契约测试 `tests/unit/domain/` |
| STD-DATA-05 | 集成测试跑独立 `*_test` 库，禁止静默 skip | `scripts/test-db.sh` + CI |
| STD-SEC-01 | 身份与租户只从认证上下文获取，正文出现身份字段即拒绝 | `tests/unit/tools/test_gateway.py` |
| STD-SEC-02 | 非开发/测试环境 Cookie 必须 `Secure` + `HttpOnly` + `SameSite=Lax` | `tests/unit/test_csrf.py` |
| STD-SEC-03 | 写请求必须校验 `Origin`，跨源拒绝且无副作用 | `backend/api/csrf.py` + 测试 |
| STD-SEC-06 | 入库内容必须过密钥扫描 | `scripts/check-secrets.py`（pre-commit + CI） |
| STD-TEST-02 | 测试名内嵌 `_AC_XX`，一个测试只追溯一个 AC | `tests/unit/test_naming_convention.py` |
| STD-TEST-05 | 突变分数：Workflow/Gateway ≥80%，Policy/领域映射 ≥70% | `scripts/mutation.sh`（G3） |
| STD-GIT-01 | 提交遵循 Conventional Commits | `.githooks/commit-msg` |
| STD-DOC-01 | 状态只有一处写入，其余派生；状态页不记录历史过程 | `scripts/check-status.py` + 评审 |
| STD-FE-01 | 前端代码遵守[前端规范](frontend.md)；接口类型只来自生成物且不可手改；改动须通过 lint/format/typecheck/test/build | `scripts/check-contracts.sh` + `scripts/verify.sh` |
| STD-AI-01 | 开工复述状态，结束更新事实源 | `AGENTS.md` + `scripts/check-status.py` |

## 新增规则

1. 同类错误出现第二次才写；第一次只修问题。
2. 必须同时给出强制点；写不出强制点就写成“建议”，不进默认上下文。
3. 30 天内没有强制点的规则自动删除；新增一条必须删除或合并一条。
