"""F-34：提交恢复与可观测（AC-67）。

- 提交超时/非法响应/未知：进入结果未知，按幂等键核实，最多 3 次退避后收敛。
- 只有明确状态才推进；不猜成功或失败；恢复查询自身超时也只重试。
- 恢复并发只一个推进，另一个幂等返回或 409，不触发第二次提交。
- 已受理不是永久终态：刷新继续推进；进入终态后重复刷新不再调用 OMS。
- 最终收敛到“已受理/已取消/被拒绝/转人工”之一，状态与文案一致。
"""

from typing import Any

import pytest

from backend.adapters.oms.faults import FaultRule
from backend.platform import metrics
from tests.integration.cancellation_support import (
    ORDERS,
    api_client,
    cancellation_app,
    confirm_cancellation,
    create_cancellation,
    refresh_cancellation,
    task_rows,
)
from tests.integration.customer_support import cleanup_customer_db, prepare_customer_db
from tests.integration.db_utils import db_available
from tests.integration.order_query_support import login

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")

TENANT = "tenant-a"
CONVERGED = {"ACCEPTED", "CANCELLED", "REJECTED", "MANUAL_REVIEW"}


@pytest.fixture(autouse=True)
def demo_customers() -> Any:
    prepare_customer_db()
    yield
    cleanup_customer_db()


@pytest.fixture(autouse=True)
def clean_metrics() -> Any:
    metrics.reset()
    yield
    metrics.reset()


def counter(name: str, **labels: str) -> int:
    """按标签字母序拼 key；无标签时与 `metrics.snapshot()` 的裸指标名一致。"""
    if not labels:
        return metrics.snapshot().get(name, 0)
    key = name + "{" + ",".join(f'{item}="{value}"' for item, value in sorted(labels.items())) + "}"
    return metrics.snapshot().get(key, 0)


def _app(**overrides: Any) -> Any:
    # 退避归零：本文件只验证“重试次数与收敛结果”，不验证真实等待时长。
    return cancellation_app(retry_backoff_seconds=0, **overrides)


def _confirm_with_submit_fault(kind: str) -> tuple[Any, Any, dict[str, Any]]:
    app = _app()
    app.state.oms.faults.add(FaultRule(kind=kind, tool="submit_cancel", times=1))
    with api_client(app) as api:
        login(api)
        created = create_cancellation(api).json()
        response = confirm_cancellation(api, created["id"])
    return app, response, created


def test_提交超时核实耗尽转人工_AC_67() -> None:
    """提交超时且结果查询持续失败：只按幂等键查 3 次，收敛到转人工。"""
    app = _app()
    app.state.oms.faults.add(FaultRule(kind="timeout", tool="submit_cancel", times=1))
    app.state.oms.faults.add(FaultRule(kind="unavailable", tool="get_cancel_result", times=10))
    with api_client(app) as api:
        login(api)
        created = create_cancellation(api).json()
        response = confirm_cancellation(api, created["id"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "MANUAL_REVIEW"
    assert body["status_text"] == "已转人工处理"
    assert body["can_confirm"] is False
    # 一次提交 + 三次核实，不重复提交、不猜结果。
    assert app.state.oms.calls["submit_cancel"] == 1
    assert app.state.oms.calls["get_cancel_result"] == 3

    [row] = task_rows()
    assert row.state == "MANUAL_REVIEW"
    assert row.last_error_code == "DEPENDENCY_UNAVAILABLE"
    assert counter("cancel_unknown_total") == 1
    assert counter("cancel_total", state="MANUAL_REVIEW") == 1
    assert "cancel_submit_latency_ms_total" in metrics.snapshot()


def test_非法响应不猜成功或失败_AC_67() -> None:
    """OMS 返回非法响应：按未知处理并核实，耗尽后转人工，不落 ACCEPTED/REJECTED。"""
    app, response, _ = _confirm_with_submit_fault("invalid_response")
    # 非法响应发生在写结果之前，核实只能拿到“查无”，因此不许猜成功或拒绝。
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "MANUAL_REVIEW"
    assert app.state.oms.calls["submit_cancel"] == 1
    assert app.state.oms.calls["get_cancel_result"] == 3
    [row] = task_rows()
    assert row.state == "MANUAL_REVIEW"
    assert row.last_error_code == "NOT_FOUND_OR_UNAUTHORIZED"


def test_恢复查询超时后核实到受理_AC_67() -> None:
    """提交回包丢失后首次核实超时：继续按同一幂等键重试，收敛到已受理。

    本用例用默认配置（ambient：退避 1s）跑一次，证明恢复参数确实来自配置；
    其余用例用 override 归零退避，只验证次数与收敛。
    """
    app = cancellation_app()
    app.state.oms.faults.add(FaultRule(kind="lost_response", tool="submit_cancel", times=1))
    app.state.oms.faults.add(FaultRule(kind="timeout", tool="get_cancel_result", times=1))
    with api_client(app) as api:
        login(api)
        created = create_cancellation(api).json()
        response = confirm_cancellation(api, created["id"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "ACCEPTED"
    assert body["status_text"] == "已受理，等待最终取消结果"
    assert app.state.oms.calls["submit_cancel"] == 1
    assert app.state.oms.calls["get_cancel_result"] == 2


def test_恢复并发只一个推进_AC_67() -> None:
    """已受理任务被并发刷新：只允许一次状态推进，另一次幂等返回或 409。"""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from fastapi.testclient import TestClient

    app = _app()
    with api_client(app) as api:
        login(api)
        created = create_cancellation(api).json()
        confirm_cancellation(api, created["id"])
        [row] = task_rows()
        app.state.oms.set_cancel_result(TENANT, row.idempotency_key, "CANCELLED")
        token = api.cookies.get("csid")
    assert token
    barrier = threading.Barrier(2)

    def attempt() -> tuple[int, dict[str, Any]]:
        client_app = _app()
        # 共享同一 OMS 与结果：并发刷新必须命中同一任务与同一幂等键。
        client_app.state.oms = app.state.oms
        client_app.state.cancel_gateway = app.state.cancel_gateway
        with TestClient(client_app) as client:
            client.cookies.set("csid", token)
            barrier.wait(timeout=10)
            response = refresh_cancellation(client, created["id"])
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))

    statuses = sorted(status for status, _ in results)
    assert statuses in ([200, 200], [200, 409]), results
    for status, body in results:
        if status == 200:
            assert body["state"] == "CANCELLED", body
        else:
            assert body["code"] == "CANCELLATION_CONFLICT", body

    [row] = task_rows()
    assert row.state == "CANCELLED"
    assert app.state.oms.calls["submit_cancel"] == 1


def test_终态后刷新不再调用OMS_AC_67() -> None:
    """已取消是终态：重复刷新幂等返回，不再按幂等键查询，也不重新提交。"""
    app = _app()
    with api_client(app) as api:
        login(api)
        created = create_cancellation(api).json()
        confirm_cancellation(api, created["id"])
        [row] = task_rows()
        app.state.oms.set_cancel_result(TENANT, row.idempotency_key, "CANCELLED")
        first = refresh_cancellation(api, created["id"])
        queries = app.state.oms.calls["get_cancel_result"]
        second = refresh_cancellation(api, created["id"])

    assert first.json()["state"] == second.json()["state"] == "CANCELLED"
    assert second.status_code == 200
    assert app.state.oms.calls["get_cancel_result"] == queries
    assert app.state.oms.calls["submit_cancel"] == 1


def test_列表回显任务id供刷新_AC_67() -> None:
    """已受理任务的列表项带任务 id：结果卡关闭后页面仍能发起结果刷新。"""
    app = _app()
    with api_client(app) as api:
        login(api)
        created = create_cancellation(api).json()
        confirm_cancellation(api, created["id"])
        listed = api.get(ORDERS)

    assert listed.status_code == 200, listed.text
    [order] = [item for item in listed.json()["orders"] if item["order_id"] == "ORD-10001"]
    cancellation = order["cancellation"]
    assert cancellation["state"] == "ACCEPTED"
    assert cancellation["id"] == created["id"]
    assert cancellation["can_confirm"] is False


def test_最终收敛可解释_AC_67() -> None:
    """提交超时后无论落在哪个结果，都只能是四种收敛状态之一且文案一致。"""
    app = _app()
    app.state.oms.faults.add(FaultRule(kind="timeout", tool="submit_cancel", times=1))
    with api_client(app) as api:
        login(api)
        created = create_cancellation(api).json()
        body = confirm_cancellation(api, created["id"]).json()

    assert body["state"] in CONVERGED
    assert body["status_text"]
    assert body["reply"].startswith(body["status_text"])
    assert app.state.oms.calls["submit_cancel"] == 1
