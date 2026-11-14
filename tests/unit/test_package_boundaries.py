"""包边界检查：把 ADR-0004 的架构约束变成可执行断言。"""

import ast
from pathlib import Path

FORBIDDEN_ROOTS = {"sqlalchemy", "asyncpg", "alembic"}
FORBIDDEN_MODULES = {"services.mock_oms"}


def imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def test_agent_runtime_does_not_import_business_or_database() -> None:
    """ADR-0004：agent_runtime 不得 import mock_oms，也不得直连数据库。"""
    root = Path("services/agent_runtime")
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        for module in imported_modules(path):
            root_package = module.split(".")[0]
            is_business = module in FORBIDDEN_MODULES or module.startswith("services.mock_oms.")
            is_database = root_package in FORBIDDEN_ROOTS
            if is_business or is_database:
                offenders.append(f"{path}: {module}")
    assert offenders == []
