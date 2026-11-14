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
    block = section(REQUIREMENTS, "### 内部状态与用户可见表达", "## 7.")
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
