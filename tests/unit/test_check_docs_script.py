"""评审记录格式检查器的自测（基座豁免）。"""

import importlib.util
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def load_module() -> Any:
    path = ROOT / "scripts" / "check-docs.py"
    spec = importlib.util.spec_from_file_location("check_docs", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_缺少评审小节时报告_基座豁免() -> None:
    module = load_module()
    missing = module.missing_review_sections("## 结论\n\n通过\n")
    assert missing == ["## 0. 门禁复核", "## 逐 AC", "## 阻断项"]


def test_完整评审通过_基座豁免() -> None:
    module = load_module()
    content = "## 0. 门禁复核\n\n## 逐 AC\n\n## 阻断项\n\n## 结论\n\n通过\n"
    assert module.missing_review_sections(content) == []


def test_路径token剥离锚点与行号_基座豁免() -> None:
    module = load_module()
    assert module.normalize_path_token("apps/workspace/lib/queue.ts#getQueue") == (
        "apps/workspace/lib/queue.ts"
    )
    assert module.normalize_path_token("backend/api/main.py:12-18") == "backend/api/main.py"
    assert module.normalize_path_token("tests/unit/test_x.py#L3") == "tests/unit/test_x.py"


def test_执行卡路径校验覆盖进行中卡片与待创建标记_基座豁免(
    tmp_path: Path, monkeypatch: Any
) -> None:
    module = load_module()
    tasks = tmp_path / "docs" / "tasks" / "001-demo"
    tasks.mkdir(parents=True)
    (tmp_path / "docs" / "STATUS.md").write_text("# 当前项目状态\n", encoding="utf-8")
    (tmp_path / "apps" / "workspace" / "lib").mkdir(parents=True)
    (tmp_path / "apps" / "workspace" / "lib" / "queue.ts").write_text(
        "export {};\n", encoding="utf-8"
    )
    card = tasks / "F-01.md"
    monkeypatch.setattr(module, "ROOT", str(tmp_path))
    monkeypatch.setattr(module, "TASKS_ROOT", str(tasks))
    monkeypatch.setattr(module, "errors", [])

    card.write_text(
        "- 状态：进行中\n\n引用 `docs/STATUS.md` 与 `apps/workspace/lib/queue.ts#getQueue`。\n",
        encoding="utf-8",
    )
    module.check_card_paths()
    assert module.errors == []

    card.write_text(
        "- 状态：进行中\n\n待创建 `apps/workspace/lib/missing.ts`。\n",
        encoding="utf-8",
    )
    module.check_card_paths()
    assert len(module.errors) == 1
    assert "apps/workspace/lib/missing.ts" in module.errors[0]

    monkeypatch.setattr(module, "errors", [])
    card.write_text(
        "- 状态：进行中\n\n待创建 `apps/workspace/lib/missing.ts`（待创建）。\n",
        encoding="utf-8",
    )
    module.check_card_paths()
    assert module.errors == []


def test_执行卡引用测试名必须真实存在_基座豁免(tmp_path: Path, monkeypatch: Any) -> None:
    module = load_module()
    tasks = tmp_path / "docs" / "tasks" / "001-demo"
    reviews = tmp_path / "docs" / "reviews" / "001-demo"
    tests = tmp_path / "tests"
    for path in (tasks, reviews, tests):
        path.mkdir(parents=True)
    (tests / "test_demo.py").write_text(
        "def test_存在_AC_35():\n    pass\n",
        encoding="utf-8",
    )
    card = tasks / "F-01.md"
    card.write_text(
        "- 状态：进行中\n\n已验证 `test_存在_AC_35`；待补 `test_不存在_AC_35`。\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "ROOT", str(tmp_path))
    monkeypatch.setattr(module, "TASKS_ROOT", str(tasks))
    monkeypatch.setattr(module, "REVIEWS_ROOT", str(reviews))
    monkeypatch.setattr(module, "TESTS_ROOT", str(tests))
    monkeypatch.setattr(module, "errors", [])

    module.check_test_references()

    assert len(module.errors) == 1
    assert "test_不存在_AC_35" in module.errors[0]


def test_AC覆盖只认表格行_基座豁免(tmp_path: Path, monkeypatch: Any) -> None:
    """brief 正文引用其他 spec 的 AC 时，不要求本 features 覆盖。"""
    module = load_module()
    spec = tmp_path / "docs" / "specs" / "001-demo"
    spec.mkdir(parents=True)
    (spec / "requirements.md").write_text(
        "# brief\n\n| AC | 场景 | 期望 |\n|---|---|---|\n| AC-01 | 场景 | 通过 |\n\n"
        "引用 003 的 AC-50~AC-58，不属于本 spec。\n",
        encoding="utf-8",
    )
    (spec / "tasks.md").write_text("| F-01 | AC-01 |\n", encoding="utf-8")
    (spec / "design.md").write_text("# plan\n", encoding="utf-8")
    monkeypatch.setattr(module, "errors", [])
    monkeypatch.setattr(module, "checked", {"acs": 0})

    module.check_ac_coverage([("001-demo", str(spec))])

    assert module.errors == []
    assert module.checked["acs"] == 1


def test_CURRENT验证块外手写计数报错_基座豁免(tmp_path: Path, monkeypatch: Any) -> None:
    module = load_module()
    docs = tmp_path / "docs"
    docs.mkdir(parents=True)
    current = docs / "STATUS.md"
    current.write_text(
        "# 当前项目状态\n\n"
        "<!-- verify:start -->\n- 最近验证：pytest 10 passed\n<!-- verify:end -->\n\n"
        "## 已完成\n\n- F-01：全量 10 passed。\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "ROOT", str(tmp_path))
    monkeypatch.setattr(module, "errors", [])

    module.check_current_handwritten_counts()

    assert len(module.errors) == 1
    assert "验证计数只能写在 verify 标记块" in module.errors[0]

    current.write_text(
        "# 当前项目状态\n\n"
        "<!-- verify:start -->\n- 最近验证：pytest 10 passed\n<!-- verify:end -->\n\n"
        "## 已完成\n\n- F-01：全量验证通过（见验证块）。\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "errors", [])
    module.check_current_handwritten_counts()
    assert module.errors == []


def test_执行卡评审节引用未创建的评审记录不算死链_基座豁免(
    tmp_path: Path, monkeypatch: Any
) -> None:
    module = load_module()
    tasks = tmp_path / "docs" / "tasks" / "001-demo"
    tasks.mkdir(parents=True)
    (tmp_path / "docs" / "STATUS.md").write_text("# 当前项目状态\n", encoding="utf-8")
    card = tasks / "F-01.md"
    monkeypatch.setattr(module, "ROOT", str(tmp_path))
    monkeypatch.setattr(module, "TASKS_ROOT", str(tasks))
    monkeypatch.setattr(module, "errors", [])

    card.write_text(
        "- 状态：待评审\n\n## 1. 改变范围\n\n引用 `docs/STATUS.md`。\n\n"
        "## 5. 评审\n\n- 评审记录：`docs/reviews/001-demo/F-01.md`\n\n"
        "## 6. 完成的定义\n\n- [ ] 评审\n",
        encoding="utf-8",
    )
    module.check_card_paths()
    assert module.errors == []

    monkeypatch.setattr(module, "errors", [])
    card.write_text(
        "- 状态：待评审\n\n## 1. 改变范围\n\n引用 `docs/missing.md`。\n\n"
        "## 5. 评审\n\n- 评审记录：`docs/reviews/001-demo/F-01.md`\n",
        encoding="utf-8",
    )
    module.check_card_paths()
    assert len(module.errors) == 1
    assert "docs/missing.md" in module.errors[0]


def test_评审结论允许加粗_基座豁免(tmp_path: Path, monkeypatch: Any) -> None:
    module = load_module()
    tasks = tmp_path / "docs" / "tasks" / "001-demo"
    reviews = tmp_path / "docs" / "reviews" / "001-demo"
    tasks.mkdir(parents=True)
    reviews.mkdir(parents=True)
    (tasks / "F-01.md").write_text(
        "---\nid: F-01\nstatus: done\n---\n\n# 任务执行卡\n", encoding="utf-8"
    )
    (reviews / "F-01.md").write_text(
        "## 0. 门禁复核\n\n## 逐 AC\n\n## 阻断项\n\n## 结论\n\n**通过**。2 轮：无阻断。\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "ROOT", str(tmp_path))
    monkeypatch.setattr(module, "REVIEWS_ROOT", str(reviews.parent))
    monkeypatch.setattr(module, "TASKS_ROOT", str(tasks.parent))
    monkeypatch.setattr(module, "errors", [])
    module.check_review_conclusions()
    assert module.errors == []


def test_验证层级缺少命令时报告_基座豁免() -> None:
    module = load_module()
    text = (
        "## 3. 验证方式\n\n```bash\n./scripts/test-db.sh tests/integration/x.py -q\n```\n\n"
        "- 测试层级：integration（x）、unit（y）\n"
    )
    assert module.verify_level_gaps(text) == ["unit"]


def test_验证层级命令齐全时通过_基座豁免() -> None:
    module = load_module()
    text = (
        "## 3. 验证方式\n\n```bash\n./scripts/test-db.sh x\n"
        "UV_CACHE_DIR=./.uv-cache uv run pytest tests/unit -q\npnpm -C apps/chat test\n```\n\n"
        "- 测试层级：integration、unit、frontend\n"
    )
    assert module.verify_level_gaps(text) == []
