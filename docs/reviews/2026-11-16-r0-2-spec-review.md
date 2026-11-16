# R0-2 规格 S1.5 评审（AC-22~29）

- 日期：2026-11-16
- 评审者：独立上下文 subagent（`r02-spec-reviewer`，未参与写作、未修改文件）
- 依据：[WORKFLOW 第 3.1 节](../process/WORKFLOW.md)、[requirements](../specs/002-backend-boundary/requirements.md)、[design](../specs/002-backend-boundary/design.md)、[tasks](../specs/002-backend-boundary/tasks.md)
- 结论：可判定（3 轮，B1–B6 全部闭合）；规格仍为等待评审，需用户批准

## 1. 轮次

| 轮次 | 结论 | 主要问题 |
|---|---|---|
| 第 1 轮 | 退回 | B1 全局 AC 命名门禁只认 001；B2 检查器无临时目录注入点；B3 契约等价不可测；B4 启动失败与 URL 判定不闭合；B5 DB 快照可能为空；B6 回滚证据不可执行 |
| 第 2 轮 | 退回 | 仅剩 B4 残留：development/test 非空非法 URL 的规则冲突 |
| 第 3 轮 | 可判定 | B4 闭合；AC-26 可判定 |

## 2. 逐 AC

| AC | 结论 | 证据 |
|---|---|---|
| AC-22 | 可判定 | `find_violations(root)` + `--root`，临时目录可直接断言 |
| AC-23 | 可判定 | 检查器 R1 + 收口后 import 数 0 |
| AC-24 | 可判定 | 检查器 R2 + 具体 Adapter 禁止 |
| AC-25 | 可判定 | 契约矩阵 + `MockTransport` 注入 + 统一错误类型 |
| AC-26 | 可判定 | `create_app(settings)` + URL 校验 + 9 格判定表 |
| AC-27 | 可判定 | `app.openapi()` 快照，T-22 移动前捕获 |
| AC-28 | 可判定 | 显式导入 `platform.models`，断言表数 > 0 |
| AC-29 | 可判定 | 起点/结束 SHA、命令、退出码、基线有效条目 0 |

## 3. 阻断项关闭

| ID | 修复 |
|---|---|
| B1 | T-22 更新 `test_naming_convention.py` 扫描全部 `docs/specs/*/requirements.md`，断言并集非空、编号不重复 |
| B2 | 检查器增加 `find_violations(root)` 与 `--root/--baseline`；AC-22 用临时目录 |
| B3 | AC-25 增加 8 类契约用例；Http Adapter 可注入 `httpx.Client(MockTransport)`；不新增异常类 |
| B4 | URL 校验对所有环境生效；requirements 6.1、FR-05、AC-26 与 design 5.4/6 同步 |
| B5 | T-27 先导入 `services.platform.models` 并断言表数 > 0，再比对快照 |
| B6 | 回滚对象改为 R0-2 起点到结束 SHA；基线出口统一为“只保留注释、有效条目 0”；T-26 更新 `verify.sh` 的 `prod import` 冒烟 |

## 4. 检查证据

```text
$ python3 scripts/check-docs.py
文档检查通过：85 个文件、72 条链接、2 个规格目录、29 条 AC、21 张执行卡跳过

$ python3 scripts/trace.py --strict
追溯检查通过：29 条 AC，8 条已登记基线

$ ./.venv/bin/ruff format --check docs/specs/002-backend-boundary/
3 files already formatted
```

## 结论

S1.5 通过（可判定）。AC-22~29 均可由测试或命令判定；阻断项 B1–B6 已关闭。规格需用户批准后进入 S4 执行卡与实现。
