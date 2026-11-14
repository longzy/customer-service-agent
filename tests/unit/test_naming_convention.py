"""测试命名约定：业务测试必须内嵌唯一的 AC 编号。

约定见 docs/process/tdd.md 第 4 节：测试名形如 `test_<中文行为>_AC_07`。
连字符形式（`_AC-07`）不是合法标识符，会导致语法错误。
"""

import ast
import re
from pathlib import Path

DOMAIN_TESTS = Path("tests/unit/domain")
NAME_PATTERN = re.compile(r"^test_.+_AC_\d{2}$")


def collect_test_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    ]


def test_业务测试名必须内嵌AC编号() -> None:
    offenders: list[str] = []
    for path in sorted(DOMAIN_TESTS.rglob("test_*.py")):
        for name in collect_test_names(path):
            if not NAME_PATTERN.match(name):
                offenders.append(f"{path}: {name}")
    assert offenders == [], "以下测试名缺少 _AC_xx 后缀：" + "；".join(offenders)
