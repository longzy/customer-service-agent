"""故障规则引擎：按工具、订单与次数匹配故障。

规则通过开发期接口 `/_admin/faults` 注册，测试结束后必须清理，避免互相污染。
"""

from dataclasses import dataclass
from typing import Literal

FaultKind = Literal["timeout", "lost_response", "invalid_response", "unavailable", "delay"]
KINDS = {"timeout", "lost_response", "invalid_response", "unavailable", "delay"}


@dataclass
class FaultRule:
    kind: str
    tool: str | None = None
    order_id: str | None = None
    times: int = 1
    delay_ms: int = 0

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"未知故障类型：{self.kind}")
        if self.times < 1:
            raise ValueError("times 必须为正整数")

    def matches(self, tool: str, order_id: str | None) -> bool:
        if self.tool is not None and self.tool != tool:
            return False
        return self.order_id is None or self.order_id == order_id


class FaultEngine:
    """规则按注册顺序匹配，命中一次消耗一次。"""

    def __init__(self) -> None:
        self._rules: list[FaultRule] = []
        self._last_delay_ms = 0

    def add(self, rule: FaultRule) -> None:
        self._rules.append(rule)

    def clear(self) -> None:
        self._rules.clear()

    @property
    def take_delay_seconds(self) -> float:
        return self._last_delay_ms / 1000

    def take(self, tool: str, order_id: str | None = None) -> str | None:
        for rule in self._rules:
            if rule.times > 0 and rule.matches(tool, order_id):
                rule.times -= 1
                self._last_delay_ms = rule.delay_ms
                return rule.kind
        return None
