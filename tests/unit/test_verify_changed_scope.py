"""verify-changed 按路径触发检查的回归测试（不新增 AC）。"""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify-changed.sh"


def _plan(tmp_path: Path, paths: list[str]) -> str:
    listing = tmp_path / "paths.txt"
    listing.write_text("\n".join(paths) + "\n", encoding="utf-8")
    result = subprocess.run(  # noqa: S603 - 固定 /bin/sh 与仓库内脚本，输入来自 tmp_path
        ["/bin/sh", str(SCRIPT), f"--paths-file={listing}", "--dry-run"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_workspace_change_skips_backend_and_chat(tmp_path: Path) -> None:
    out = _plan(tmp_path, ["apps/workspace/features/queue/components/QueueToolbar.tsx"])

    assert "运行：workspace 前端" in out
    assert "跳过：chat 前端（无相关变更）" in out
    assert "跳过：Python 静态检查（ruff）（无相关变更）" in out
    assert "跳过：后端类型检查（mypy）（无相关变更）" in out
    assert "跳过：后端测试（无相关变更）" in out
    assert "跳过：契约生成物（无相关变更）" in out


def test_backend_change_runs_backend_only(tmp_path: Path) -> None:
    out = _plan(tmp_path, ["backend/api/main.py"])

    assert "运行：Python 静态检查（ruff）" in out
    assert "运行：后端类型检查（mypy）" in out
    assert "运行：后端测试" in out
    assert "跳过：chat 前端（无相关变更）" in out
    assert "跳过：workspace 前端（无相关变更）" in out
    assert "跳过：文档引用（无相关变更）" in out


def test_docs_change_skips_code_checks(tmp_path: Path) -> None:
    out = _plan(tmp_path, ["docs/CURRENT.md"])

    assert "运行：文档引用" in out
    assert "运行：状态一致性" in out
    assert "运行：追溯矩阵" in out
    assert "跳过：Python 静态检查（ruff）（无相关变更）" in out
    assert "跳过：chat 前端（无相关变更）" in out
    assert "跳过：workspace 前端（无相关变更）" in out


def test_contract_change_runs_contract_check_only(tmp_path: Path) -> None:
    out = _plan(tmp_path, ["packages/contracts/openapi.json"])

    assert "运行：契约生成物" in out
    assert "跳过：chat 前端（无相关变更）" in out
    assert "跳过：workspace 前端（无相关变更）" in out
    assert "跳过：Python 静态检查（ruff）（无相关变更）" in out


def test_both_frontends_run_independently(tmp_path: Path) -> None:
    out = _plan(
        tmp_path,
        [
            "apps/chat/features/chat/components/ChatShell.tsx",
            "apps/workspace/features/queue/components/QueueToolbar.tsx",
        ],
    )

    assert "运行：chat 前端" in out
    assert "运行：workspace 前端" in out
    assert "跳过：Python 静态检查（ruff）（无相关变更）" in out
    assert "跳过：后端测试（无相关变更）" in out


def test_tests_change_runs_pytest_but_not_mypy(tmp_path: Path) -> None:
    out = _plan(tmp_path, ["tests/unit/test_verify_changed_scope.py"])

    assert "运行：后端测试" in out
    assert "跳过：后端类型检查（mypy）（无相关变更）" in out
    assert "跳过：chat 前端（无相关变更）" in out
    assert "跳过：workspace 前端（无相关变更）" in out
