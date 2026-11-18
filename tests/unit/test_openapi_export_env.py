"""回归：CI 没有 .env 时 OpenAPI 导出也必须成功（首次全量 CI 在此失败过）。"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_ENV_VARS = (
    "ENVIRONMENT",
    "DATABASE_URL",
    "OMS_BASE_URL",
    "MODEL_API_KEY",
    "M1_ENABLED",
)


def test_openapi导出不依赖本地env_基座豁免(tmp_path: Path) -> None:
    # cwd 放到空目录，Settings 读不到 .env；同时清掉可能生效的环境变量。
    env = {key: value for key, value in os.environ.items() if key not in CONFIG_ENV_VARS}
    result = subprocess.run(  # noqa: S603 - 固定解释器与仓库内脚本
        [sys.executable, str(ROOT / "scripts" / "export_openapi.py"), "--check"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "OpenAPI 契约一致" in result.stdout
