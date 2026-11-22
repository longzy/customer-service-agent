"""任务卡模板与证据门禁的契约测试（基座豁免）。

模板（事实源）与 `check-docs.py`（门禁）必须表达同一口径：§4 含可复核的
命令输出代码块，全量计数引用 CURRENT。任一侧改动而另一侧未同步时，这里先红。
"""

import importlib.util
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "docs" / "templates" / "task-design-card.md"


def load_check_docs() -> Any:
    path = ROOT / "scripts" / "check-docs.py"
    spec = importlib.util.spec_from_file_location("check_docs", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evidence_section() -> str:
    content = TEMPLATE.read_text(encoding="utf-8")
    assert "## 4. 证据" in content
    return content.split("## 4. 证据", 1)[1].split("\n## ", 1)[0]


def test_任务卡模板证据段能通过门禁_基座豁免() -> None:
    assert load_check_docs().evidence_has_command_output(evidence_section())


def test_任务卡模板证据段缺命令输出时门禁失败_基座豁免() -> None:
    without_code = re.sub(r"```.*?```", "", evidence_section(), flags=re.S)
    assert not load_check_docs().evidence_has_command_output(without_code)
