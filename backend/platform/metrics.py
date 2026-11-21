"""进程内计数器：最小可用的指标出口，供 /metrics 暴露 Prometheus 文本。

无标签计数沿用 `increment`/`snapshot`；需要维度时用 `increment_labeled`，
渲染时按指标名分组输出一条 TYPE 与多行样本，避免把标签拼进 TYPE 行。
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from threading import Lock

Labels = tuple[tuple[str, str], ...]

_lock = Lock()
_counters: Counter[str] = Counter()
_labeled_counters: Counter[tuple[str, Labels]] = Counter()


def increment(name: str, amount: int = 1) -> None:
    """线程安全累加；计数只增不减，进程重启归零。"""
    with _lock:
        _counters[name] += amount


def increment_labeled(name: str, labels: Mapping[str, str], amount: int = 1) -> None:
    """带标签的计数器；标签集合固定、值由调用方保证取自有限集合。"""
    key = tuple(sorted((str(item), str(value)) for item, value in labels.items()))
    with _lock:
        _labeled_counters[(name, key)] += amount


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _label_text(key: Labels) -> str:
    return ",".join(f'{name}="{_escape(value)}"' for name, value in key)


def _flatten(name: str, key: Labels) -> str:
    return f"{name}{{{_label_text(key)}}}"


def snapshot() -> dict[str, int]:
    """无标签计数原样返回；标签计数拍平为 `name{k="v"}`，便于断言。"""
    with _lock:
        flat = dict(_counters)
        for (name, key), value in _labeled_counters.items():
            flat[_flatten(name, key)] = value
        return flat


def reset() -> None:
    """测试专用：清空进程内计数。"""
    with _lock:
        _counters.clear()
        _labeled_counters.clear()


def render() -> str:
    """输出 Prometheus 文本格式；只含 counter 类型。"""
    with _lock:
        counters = dict(_counters)
        labeled = dict(_labeled_counters)
    lines: list[str] = []
    for name, value in sorted(counters.items()):
        lines.append(f"# TYPE {name} counter")
        lines.append(f"{name} {value}")
    grouped: dict[str, list[tuple[Labels, int]]] = {}
    for (name, key), value in labeled.items():
        grouped.setdefault(name, []).append((key, value))
    for name in sorted(grouped):
        lines.append(f"# TYPE {name} counter")
        for key, value in sorted(grouped[name]):
            lines.append(f"{_flatten(name, key)} {value}")
    return "\n".join(lines) + ("\n" if lines else "")
