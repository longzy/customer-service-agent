# 合并门：分支保护与 main-guard

- 状态：草案（2026-11-22，待用户确认后转已批准）
- 用途：说明 `main` 的合并门禁、当前套餐限制与补偿控制。
- 依据：[WORKFLOW](../process/WORKFLOW.md) G2/G3、[CI](../../.github/workflows/ci.yml)

## 目标

`main` 只接受经过 PR、CI 全量绿、独立评审且 CODEOWNERS 同意的合并。这需要 GitHub 的
rulesets / branch protection；当前私有仓库套餐可能不提供 required checks。

## 优先方案：rulesets

有权限时，用规则集要求：

- 只能通过 PR 合并，禁止直推与 force push；
- required checks：`verify`（全量）、`main-guard`、`mutation`；`audit` 阻断 high/critical；
- required review：至少 1 名 CODEOWNERS，且评审者未参与实现；
- 合并后删除分支、要求线性历史（按团队习惯）。

示例（按 owner/repo 替换，先 `gh auth login`）：

```bash
gh api -X POST repos/OWNER/REPO/rulesets --input - <<'JSON'
{
  "name": "main-protection",
  "target": "branch",
  "enforcement": "active",
  "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
  "rules": [
    {"type": "pull_request", "parameters": {
      "required_approving_review_count": 1,
      "require_code_owner_review": true,
      "dismiss_stale_reviews_on_push": true,
      "require_last_push_approval": true
    }},
    {"type": "required_status_checks", "parameters": {
      "strict_required_status_checks_policy": true,
      "required_status_checks": [
        {"context": "verify"},
        {"context": "main-guard"},
        {"context": "mutation"}
      ]
    }},
    {"type": "non_fast_forward"},
    {"type": "deletion"}
  ]
}
JSON
```

## 本地流程（2026-11-22 起）

1. `git switch -c <type>/<slug>` 从最新 `main` 开分支；
2. 小步提交，提交信息按 `type(F-XX): 中文描述`；
3. `git push -u origin <branch>`；
4. `gh pr create --fill`（先 `gh auth login`；`gh` 不可用时用网页创建 PR）；
5. PR 描述贴门禁证据；等 CI 绿与独立评审通过后合并，不直推 `main`。

`.githooks/pre-push` 对 `main` 分支会打印警告，但不阻断；这是套餐限制下的补偿信号，不是硬门禁。

## 补偿方案：main-guard

套餐不允许 required checks 时：

- PR 仍是唯一合并方式（人工约定）；
- `.github/workflows/main-guard.yml` 在 push 到 `main` 后检查提交是否关联已合并 PR；
  直推会失败并通知 owner，但**不能阻止**推送；
- 因此 `STATUS.md` 的「阻塞」必须如实登记“合并门未强制”，不能声称已有硬门禁；
- 条件允许时，第一步启用 rulesets，第二步再评估 merge queue。

## 验证

- `gh api repos/OWNER/REPO/rulesets` 能看到 `main-protection`；
- 直推一次测试分支到 `main`，`main-guard` 应变红；
- PR 合并后 `main-guard` 应绿。
