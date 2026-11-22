"""门禁放置与合并门契约：全量只在收口/CI，评审用定向检查。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRE_PUSH = ROOT / ".githooks" / "pre-push"
WORKFLOW = ROOT / "docs" / "process" / "WORKFLOW.md"
REVIEW_CHECKLIST = ROOT / "docs" / "process" / "review-checklist.md"
REVIEW_TEMPLATE = ROOT / "docs" / "templates" / "review.md"
TASK_TEMPLATE = ROOT / "docs" / "templates" / "task-design-card.md"
REVIEW_PACK = ROOT / "scripts" / "review_pack.py"
MAIN_GUARD = ROOT / ".github" / "workflows" / "main-guard.yml"
BRANCH_DOC = ROOT / "docs" / "ops" / "branch-protection.md"


def test_pre_push复用全量结果_基座豁免() -> None:
    text = PRE_PUSH.read_text(encoding="utf-8")
    assert "verify.sh --reuse" in text


def test_全量只在收口与CI执行_基座豁免() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "送审前跑一次" not in workflow
    assert "全量只在收口 `make verify` 跑一次" in workflow
    assert "make verify-check` 是手动全量/CI 等价入口" in workflow


def test_评审检查不再要求全量_基座豁免() -> None:
    checklist = REVIEW_CHECKLIST.read_text(encoding="utf-8")
    assert "主评审跑 `make verify-changed`" in checklist
    assert "全量由收口 `make verify` 执行" in checklist

    review = REVIEW_TEMPLATE.read_text(encoding="utf-8")
    assert "收口全量（回填）" in review
    assert "先跑 `make verify-check`" not in review

    task = TASK_TEMPLATE.read_text(encoding="utf-8")
    assert "make verify-changed ARGS=F-XX` exit 0" in task
    assert "make verify-check` exit 0" not in task


def test_评审包命令不含全量_基座豁免() -> None:
    source = REVIEW_PACK.read_text(encoding="utf-8")
    assert '"make verify-check"' not in source
    assert "make verify-changed ARGS" in source


def test_合并门有main_guard与分支保护文档_基座豁免() -> None:
    guard = MAIN_GUARD.read_text(encoding="utf-8")
    assert "commits/${GITHUB_SHA}/pulls" in guard
    assert "merged_at" in guard
    doc = BRANCH_DOC.read_text(encoding="utf-8")
    assert "rulesets" in doc
    assert "main-guard" in doc


def test_spec门禁接入验证链_基座豁免() -> None:
    for relative in (".githooks/pre-commit", "scripts/review-check.sh", "scripts/verify.sh"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "check-spec.py" in text, relative
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "check-spec:" in makefile


def test_全量突变重建副本_基座豁免() -> None:
    text = (ROOT / "scripts" / "mutation.sh").read_text(encoding="utf-8")
    assert "rm -rf mutants .mutmut-cache" in text
