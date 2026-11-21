# <feature> 任务

> 本文件由 `scripts/gen_tasks.py` 从执行卡 frontmatter 生成，不要手改。
> 新增或调整任务：先改执行卡，再运行 `make gen-tasks`。

- 状态：草案
- 日期：YYYY-MM-DD
- 依据：`requirements.md`、`design.md`
- 构建顺序：F-XX → F-YY；一次只做一个，状态由执行卡 frontmatter 决定。
- 状态源：`docs/tasks/<spec>/F-XX.md` 的 frontmatter

<!-- gen:start -->
| ID | 任务 | AC | 状态 | 卡片 |
|---|---|---|---|---|
| F-XX | <一句话，不超过 40 字> | AC-XX | 未开始 | `tasks/<spec>/F-XX.md` |
| F-YY | <一句话，不超过 40 字> | AC-YY | 未开始 | `tasks/<spec>/F-YY.md` |
<!-- gen:end -->
