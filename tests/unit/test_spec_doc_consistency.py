"""规格文档与代码的一致性（AC-16）。

把"文档说一套、代码做一套"变成可执行检查：
1. requirements.md 的状态清单与代码枚举一致；
2. requirements.md 的对外表达表与代码映射一致；
3. ui.md 覆盖全部取消状态；
4. acceptance.md 的 AC 编号连续且唯一。
"""

import re
from pathlib import Path

from services.api.domain.cancellation import EXPRESSIONS, CancellationState
from services.api.domain.orders import OrderStatus

SPEC_DIR = Path("docs/specs/M1/001-order-cancel")
REQUIREMENTS = (SPEC_DIR / "requirements.md").read_text(encoding="utf-8")
UI = (SPEC_DIR / "ui.md").read_text(encoding="utf-8")
ACCEPTANCE = (SPEC_DIR / "acceptance.md").read_text(encoding="utf-8")


def section(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    return text[begin : text.index(end, begin)]


def test_取消状态清单与代码枚举一致_AC_16() -> None:
    block = section(REQUIREMENTS, "### 取消任务状态", "### 内部状态与用户可见表达")
    documented = set(re.findall(r"^- `([A-Z_]+)`：", block, re.M))
    assert documented == {state.value for state in CancellationState}


def test_订单状态清单与代码枚举一致_AC_16() -> None:
    block = section(REQUIREMENTS, "### 订单状态（Mock OMS）", "### 取消任务状态")
    documented = set(re.findall(r"^- `([A-Z_]+)`：", block, re.M))
    assert documented == {status.value for status in OrderStatus}


def test_对外表达表与代码映射一致_AC_16() -> None:
    block = section(REQUIREMENTS, "### 内部状态与用户可见表达", "## 10.")
    documented = dict(re.findall(r"^\| `([A-Z_]+)` \| (.+?) \|$", block, re.M))
    actual = {state.value: text for state, text in EXPRESSIONS.items()}
    assert documented == actual


def test_界面规格覆盖全部取消状态_AC_16() -> None:
    mentioned = set(re.findall(r"`([A-Z_]+)`", UI))
    missing = {state.value for state in CancellationState} - mentioned
    assert missing == set(), f"ui.md 未覆盖以下状态：{sorted(missing)}"


def test_验收用例编号连续且唯一_AC_16() -> None:
    ids = re.findall(r"^\| (AC-\d{2}) \|", ACCEPTANCE, re.M)
    assert len(ids) == len(set(ids)), "AC 编号重复"
    assert ids == [f"AC-{index:02d}" for index in range(1, len(ids) + 1)], "AC 编号不连续"


FUNCTIONAL = section(REQUIREMENTS, "## 3. 功能需求", "## 4. 非功能需求")


def test_功能需求使用EARS句式_AC_16() -> None:
    """每条功能需求都必须包含 THE SYSTEM SHALL，才能直接转成测试。"""
    lines = [line for line in FUNCTIONAL.splitlines() if line.startswith("- ") and "SHALL" in line]
    assert lines, "功能需求中没有找到 EARS 句式"
    missing = [
        line for line in FUNCTIONAL.splitlines() if line.startswith("- ") and "SHALL" not in line
    ]
    assert missing == [], f"以下需求缺少 THE SYSTEM SHALL：{missing}"


def test_每条功能需求至少被一条验收用例覆盖_AC_16() -> None:
    frs = set(re.findall(r"\bFR-\d{2}\b", FUNCTIONAL))
    rows = re.findall(r"^\| (AC-\d{2}) \|.*?\| (.*?) \|\s*$", ACCEPTANCE, re.M)
    covered = set()
    for _ac, fr_cell in rows:
        covered |= set(re.findall(r"\bFR-\d{2}\b", fr_cell))
    assert frs - covered == set(), f"以下需求没有验收用例覆盖：{sorted(frs - covered)}"


def test_每个用户故事含优先级与验收场景_AC_16() -> None:
    stories = section(REQUIREMENTS, "## 2. 用户故事与验收场景", "## 3. 功能需求")
    blocks = [b for b in re.split(r"^### ", stories, flags=re.M)[1:] if b.startswith("US-")]
    assert blocks, "未找到用户故事"
    for block in blocks:
        title = block.splitlines()[0]
        assert "优先级" in block, f"{title} 缺少优先级"
        assert "独立测试" in block, f"{title} 缺少独立测试说明"
        assert "验收场景" in block, f"{title} 缺少验收场景"
        assert "Given" in block, f"{title} 的验收场景未使用 Given/When/Then"
