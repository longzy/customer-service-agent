"""进程内指标：带标签计数与 Prometheus 文本输出。"""

import pytest

from backend.platform import metrics


@pytest.fixture(autouse=True)
def reset_metrics() -> None:
    metrics.reset()
    yield
    metrics.reset()


def test_带标签计数按指标名分组输出_AC_57() -> None:
    metrics.increment_labeled("order_query_total", {"tool": "get_order", "status": "ok"})
    metrics.increment_labeled(
        "order_query_total", {"tool": "list_recent_orders", "status": "not_found"}
    )
    metrics.increment_labeled("order_query_total", {"tool": "get_order", "status": "ok"})
    metrics.increment("trace_started_total")

    text = metrics.render()
    # TYPE 行只出现一次，标签在样本行。
    assert text.count("# TYPE order_query_total counter") == 1
    assert 'order_query_total{status="ok",tool="get_order"} 2' in text
    assert 'order_query_total{status="not_found",tool="list_recent_orders"} 1' in text
    assert "# TYPE trace_started_total counter" in text
    # snapshot 用同一种拍平格式，测试可直接断言。
    assert metrics.snapshot()['order_query_total{status="ok",tool="get_order"}'] == 2


def test_无标签与带标签计数互不影响_AC_57() -> None:
    metrics.increment("order_query_latency_ms_total", 12)
    metrics.increment_labeled("order_query_unbound_total", {"tool": "get_order"})

    snapshot = metrics.snapshot()
    assert snapshot["order_query_latency_ms_total"] == 12
    assert snapshot['order_query_unbound_total{tool="get_order"}'] == 1


def test_标签值转义引号与反斜杠() -> None:
    metrics.increment_labeled("demo_total", {"label": 'a"b\\c'})

    assert 'demo_total{label="a\\"b\\\\c"} 1' in metrics.render()


def test_reset清空两类计数() -> None:
    metrics.increment("plain_total")
    metrics.increment_labeled("labeled_total", {"tool": "get_order"})
    metrics.reset()

    assert metrics.snapshot() == {}
    assert metrics.render() == ""
