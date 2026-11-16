"""AC-22：依赖检查器可注入扫描根，并区分新增/过期基线与检查器错误。"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

CHECKER = Path("scripts/check-imports.py")


def _checker() -> ModuleType:
    assert CHECKER.exists(), "scripts/check-imports.py 尚未实现"
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


def _write(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _violations(root: Path) -> list[tuple[str, str, str]]:
    return [(item.path, item.module, item.rule) for item in _checker().find_violations(root)]


def test_new_violation_is_reported_AC_22(tmp_path: Path) -> None:
    _write(tmp_path, "services/tools/x.py", "from services.api.auth import Identity\n")

    assert _violations(tmp_path) == [("services/tools/x.py", "services.api.auth", "R1")]


def test_allowed_import_is_not_reported_AC_22(tmp_path: Path) -> None:
    _write(tmp_path, "services/tools/x.py", "from services.domain.orders import OrderDetail\n")

    assert _violations(tmp_path) == []


def test_type_checking_import_counts_AC_22(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "services/tools/x.py",
        "from typing import TYPE_CHECKING\n"
        "\n"
        "if TYPE_CHECKING:\n"
        "    from services.api.auth import Identity\n",
    )

    assert _violations(tmp_path) == [("services/tools/x.py", "services.api.auth", "R1")]


def test_relative_parent_import_is_resolved_AC_22(tmp_path: Path) -> None:
    _write(tmp_path, "services/tools/x.py", "from ..api import auth\n")

    assert _violations(tmp_path) == [("services/tools/x.py", "services.api", "R1")]


def test_package_from_import_is_reported_AC_22(tmp_path: Path) -> None:
    _write(tmp_path, "services/api/__init__.py", "")
    _write(tmp_path, "services/tools/x.py", "from services import api\n")

    assert ("services/tools/x.py", "services.api", "R1") in _violations(tmp_path)


def test_package_from_import_mock_oms_is_reported_AC_22(tmp_path: Path) -> None:
    _write(tmp_path, "services/mock_oms/__init__.py", "")
    _write(tmp_path, "services/tools/x.py", "from services import mock_oms\n")

    found = _violations(tmp_path)
    assert ("services/tools/x.py", "services.mock_oms", "R2") in found


def test_baseline_allows_known_violation_AC_22(tmp_path: Path) -> None:
    _write(tmp_path, "services/tools/x.py", "from services.api.auth import Identity\n")
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("services/tools/x.py: services.api.auth [R1] # known\n", encoding="utf-8")

    checker = _checker()
    assert checker.main(["--root", str(tmp_path), "--baseline", str(baseline), "--strict"]) == 0


def test_stale_baseline_fails_AC_22(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("services/tools/x.py: services.api.auth [R1] # stale\n", encoding="utf-8")

    checker = _checker()
    assert checker.main(["--root", str(tmp_path), "--baseline", str(baseline), "--strict"]) == 1


def test_new_violation_fails_without_strict_AC_22(tmp_path: Path) -> None:
    _write(tmp_path, "services/tools/x.py", "from services.api.auth import Identity\n")

    checker = _checker()
    assert checker.main(["--root", str(tmp_path)]) == 1


def test_cli_output_contains_file_module_rule_AC_22(tmp_path: Path, capsys) -> None:
    _write(tmp_path, "services/tools/x.py", "from services.api.auth import Identity\n")

    checker = _checker()
    assert checker.main(["--root", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert "services/tools/x.py" in captured.out
    assert "services.api.auth" in captured.out
    assert "R1" in captured.out


def test_checker_error_returns_two_AC_22(tmp_path: Path) -> None:
    _write(tmp_path, "services/tools/broken.py", "def broken(\n")

    checker = _checker()
    assert checker.main(["--root", str(tmp_path), "--strict"]) == 2


def test_repository_baseline_has_no_new_violations_AC_22() -> None:
    checker = _checker()

    assert checker.main(["--root", str(Path.cwd()), "--strict"]) == 0
