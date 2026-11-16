"""AC-24：tools/workflows 不得 import mock_oms 或具体 OMS Adapter。"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check-imports.py"


def _checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_imports", CHECKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(spec.name, None)
        raise
    return module


def test_tools_and_workflows_do_not_import_concrete_adapters_AC_24() -> None:
    checker = _checker()

    violations = checker.find_violations(ROOT)
    offenders = [(item.path, item.module) for item in violations if item.rule == "R2"]

    assert offenders == []
