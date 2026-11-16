#!/usr/bin/env python3
"""模块依赖边界检查。

用法：
    python3 scripts/check-imports.py                  # 默认即严格：新增违规/过期基线退出 1
    python3 scripts/check-imports.py --strict         # 兼容别名，与默认行为一致
    python3 scripts/check-imports.py --root PATH      # 指定扫描根（测试用）
    python3 scripts/check-imports.py --print-baseline # 输出当前基线行

退出码：0 通过；1 有新增违规或过期基线；2 检查器自身错误。
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASELINE = Path("scripts") / "import-baseline.txt"


@dataclass(frozen=True)
class Rule:
    id: str
    sources: tuple[str, ...]
    forbidden: tuple[str, ...]
    excludes: tuple[str, ...] = ()


RULES = (
    Rule(
        "R1",
        ("services/agent_runtime", "services/tools", "services/workflows"),
        ("services.api",),
    ),
    Rule(
        "R2",
        ("services/tools", "services/workflows"),
        (
            "services.mock_oms",
            "services.adapters.oms.mock",
            "services.adapters.oms.http",
        ),
    ),
    Rule(
        "R3",
        ("services/domain",),
        (
            "services.api",
            "services.platform",
            "services.identity",
            "services.adapters",
            "services.tools",
            "services.workflows",
            "sqlalchemy",
            "fastapi",
        ),
    ),
    Rule(
        "R4",
        ("services/platform",),
        (
            "services.api",
            "services.identity",
            "services.domain",
            "services.adapters",
            "services.tools",
            "services.workflows",
        ),
    ),
    Rule(
        "R5",
        ("services/adapters/oms",),
        ("services.api", "services.tools", "services.workflows"),
    ),
    Rule(
        "R6",
        ("services",),
        ("services.mock_oms",),
        ("services/mock_oms",),
    ),
)

BASELINE_PATTERN = re.compile(
    r"^(?P<path>[^:]+):\s*(?P<module>\S+)\s+\[(?P<rule>R\d+)\](?:\s*#.*)?$"
)


@dataclass(frozen=True)
class Violation:
    path: str
    module: str
    rule: str

    def key(self) -> tuple[str, str, str]:
        return (self.path, self.module, self.rule)

    def __str__(self) -> str:
        return f"{self.path}: {self.module}（{self.rule}）"


def _under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def _selected_rules(path: str) -> tuple[Rule, ...]:
    selected: list[Rule] = []
    for rule in RULES:
        if not any(_under(path, source) for source in rule.sources):
            continue
        if any(_under(path, excluded) for excluded in rule.excludes):
            continue
        selected.append(rule)
    return tuple(selected)


def _matches(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(prefix + ".")


def _module_exists(root: Path, module: str) -> bool:
    target = root.joinpath(*module.split("."))
    return target.with_suffix(".py").is_file() or target.is_dir()


def _resolve_from(path: Path, root: Path, node: ast.ImportFrom) -> list[str]:
    package = list(path.relative_to(root).with_suffix("").parts[:-1])
    if node.level:
        trim = node.level - 1
        if trim > len(package):
            return []
        if trim:
            package = package[: len(package) - trim]
    else:
        package = []
    base = ".".join(package)
    if node.module:
        module = f"{base}.{node.module}" if base else node.module
        # `from pkg import sub` 可能导入子模块；只把真实存在的 pkg.sub 纳入匹配，
        # 避免把 `from services.api.auth import Identity` 误报成模块。
        candidates = [module]
        for alias in node.names:
            candidate = f"{module}.{alias.name}"
            if _module_exists(root, candidate):
                candidates.append(candidate)
        return candidates
    return [f"{base}.{alias.name}" if base else alias.name for alias in node.names]


def _imports(path: Path, root: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.extend(_resolve_from(path, root, node))
    return sorted(set(modules))


def find_violations(root: Path) -> list[Violation]:
    """扫描 `<root>/services/**/*.py`，返回全部越界 import。"""
    root = root.resolve()
    services = root / "services"
    if not services.is_dir():
        return []
    violations: list[Violation] = []
    for path in sorted(services.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(root).as_posix()
        rules = _selected_rules(relative)
        if not rules:
            continue
        for module in _imports(path, root):
            for rule in rules:
                if any(_matches(module, prefix) for prefix in rule.forbidden):
                    violations.append(Violation(relative, module, rule.id))
    return sorted(violations, key=lambda item: item.key())


def load_baseline(path: Path) -> dict[tuple[str, str, str], str]:
    """读取基线；文件不存在或只有注释视为空基线。"""
    if not path.exists():
        return {}
    entries: dict[tuple[str, str, str], str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = BASELINE_PATTERN.match(line)
        if match is None:
            raise ValueError(f"基线第 {number} 行格式非法：{line.strip()}")
        key = (match.group("path"), match.group("module"), match.group("rule"))
        entries[key] = match.group(0)
    return entries


def run(root: Path, baseline_path: Path) -> int:
    violations = find_violations(root)
    baseline = load_baseline(baseline_path)
    keys = {item.key() for item in violations}
    new = [item for item in violations if item.key() not in baseline]
    stale = sorted(set(baseline) - keys)

    for item in violations:
        label = "基线" if item.key() in baseline else "新增"
        print(f"{label}：{item}")
    if new:
        print(f"新增违规 {len(new)} 条：", file=sys.stderr)
        for item in new:
            print(f"  - {item}", file=sys.stderr)
    if stale:
        print(f"过期基线 {len(stale)} 条（对应违规已不存在）：", file=sys.stderr)
        for path, module, rule in stale:
            print(f"  - {path}: {module}（{rule}）", file=sys.stderr)
    if new or stale:
        print(
            f"边界检查失败：新增 {len(new)}，过期基线 {len(stale)}；"
            "修复后更新 scripts/import-baseline.txt",
            file=sys.stderr,
        )
        return 1
    print(f"边界检查通过：{len(violations)} 个已知违规，基线 {len(baseline)} 条，新增 0，过期 0")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检查 services 的模块依赖边界")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--baseline", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--print-baseline", action="store_true")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    baseline = args.baseline or root / DEFAULT_BASELINE
    try:
        if args.print_baseline:
            for item in find_violations(root):
                print(f"{item.path}: {item.module} [{item.rule}]")
            return 0
        # --strict 是兼容别名；默认行为已经严格，避免本地“只报告”掩盖违规。
        _ = args.strict
        return run(root, baseline)
    except (OSError, SyntaxError, ValueError) as error:
        print(f"检查器错误：{error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
