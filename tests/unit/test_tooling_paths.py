"""工具链路径检查：配置中引用的目录必须存在。"""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_mutmut_source_paths_exist() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    paths = data["tool"]["mutmut"]["source_paths"]

    assert paths, "mutmut source_paths 不能为空"
    missing = [path for path in paths if not (ROOT / path).is_dir()]
    assert missing == [], f"mutmut source_paths 指向不存在的目录：{missing}"
