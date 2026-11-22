"""突变副本必须覆盖单测读取的仓库路径（基座豁免）。

mutmut 在 `mutants/` 里重放 `tests/unit`；`also_copy` 漏掉某个目录时，失败
表现为 clean tests 的 FileNotFoundError，而不是“配置缺项”。这里把这条约束
变成毫秒级检查：单测里引用且真实存在的根路径，必须在突变副本集合内。
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREFIXES = (
    "apps/",
    "backend/",
    "docs/",
    "evals/",
    "migrations/",
    "packages/",
    "scripts/",
    "tests/",
)
# mutmut 自己会复制 pyproject 与 uv.lock，不需要写进 also_copy。
IMPLICIT = {Path("pyproject.toml"), Path("uv.lock")}
PATH_PATTERN = re.compile(
    r"[\"']((?:" + "|".join(re.escape(prefix) for prefix in PREFIXES) + r")[^\"']+)"
    r"|[\"'](Makefile|alembic\.ini|\.githooks/[^\"']+)[\"']"
)


def _mutmut_config() -> tuple[list[Path], list[Path]]:
    document = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    config = document["tool"]["mutmut"]
    return (
        [Path(item) for item in config["source_paths"]],
        [Path(item) for item in config["also_copy"]],
    )


def _references() -> set[Path]:
    referenced: set[Path] = set()
    for path in (ROOT / "tests" / "unit").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for match in PATH_PATTERN.finditer(text):
            token = match.group(1) or match.group(2)
            candidate = Path(token.rstrip("/"))
            if (ROOT / candidate).exists():
                referenced.add(candidate)
    return referenced


def _covered(path: Path, entries: list[Path]) -> bool:
    return any(path == entry or entry in path.parents for entry in entries)


def test_突变副本覆盖单测引用的仓库路径_基座豁免() -> None:
    source_paths, also_copy = _mutmut_config()
    entries = source_paths + also_copy + list(IMPLICIT)
    missing = sorted(str(path) for path in _references() if not _covered(path, entries))
    assert missing == [], (
        "以下路径被 tests/unit 读取，但不在 mutmut 副本中；"
        f"请补到 pyproject.toml 的 [tool.mutmut].also_copy：{missing}"
    )


def test_also_copy条目真实存在_基座豁免() -> None:
    _, also_copy = _mutmut_config()
    missing = sorted(str(entry) for entry in also_copy if not (ROOT / entry).exists())
    assert missing == [], f"also_copy 指向不存在的路径：{missing}"
