"""测试隔离：本地与 CI 使用同一份配置来源，不读开发者 .env。"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_测试脚本关闭env文件读取_基座豁免() -> None:
    script = (ROOT / "scripts" / "test-db.sh").read_text(encoding="utf-8")
    assert "SETTINGS_ENV_FILE=/dev/null" in script


def test_关闭env文件后不读本地dotenv_基座豁免(tmp_path: Path) -> None:
    """没有这项隔离时，本机 .env 会让“本地绿、CI 红”重复发生。"""
    (tmp_path / ".env").write_text("MODEL_API_KEY=from-local-dotenv\n", encoding="utf-8")
    env = {key: value for key, value in os.environ.items() if key != "MODEL_API_KEY"} | {
        "PYTHONPATH": str(ROOT),
        "SETTINGS_ENV_FILE": "/dev/null",
    }
    result = subprocess.run(  # noqa: S603 - 固定解释器与仓库内模块
        [
            sys.executable,
            "-c",
            "from backend.platform.settings import settings; print(settings.model_api_key)",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_测试库默认一次性并在退出时清理_基座豁免() -> None:
    """并行评审/门禁共用固定库会互删数据；默认库名必须每次运行唯一。"""
    script = (ROOT / "scripts" / "test-db.sh").read_text(encoding="utf-8")
    assert "customer_service_test_$$" in script
    assert "DROP_ON_EXIT" in script
    assert "dropdb" in script
    assert "TEST_DB_NAME" in script
