"""进程内计数器：最小可用的指标出口，供 /metrics 暴露 Prometheus 文本。"""

from __future__ import annotations

from collections import Counter
from threading import Lock

_lock = Lock()
_counters: Counter[str] = Counter()


def increment(name: str, amount: int = 1) -> None:
    """线程安全累加；计数只增不减，进程重启归零。"""
    with _lock:
        _counters[name] += amount


def snapshot() -> dict[str, int]:
    with _lock:
        return dict(_counters)


def reset() -> None:
    """测试专用：清空进程内计数。"""
    with _lock:
        _counters.clear()


def render() -> str:
    """输出 Prometheus 文本格式；只含 counter 类型。"""
    lines: list[str] = []
    for name, value in sorted(snapshot().items()):
        lines.append(f"# TYPE {name} counter")
        lines.append(f"{name} {value}")
    return "\n".join(lines) + ("\n" if lines else "")
