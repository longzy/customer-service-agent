"""F-33：重复与并发只提交一次（AC-66）。

同一任务重复确认返回同一结果；并发确认只有一个推进，另一个幂等返回或 409；
同一订单已有进行中任务时复用当前任务；终态后再次发起按新请求走资格判定，
不重新提交旧任务。
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.conversations import customer_cancellations
from tests.integration.cancellation_support import (
    api_client,
    confirm_cancellation,
    create_cancellation,
    default_order_app,
    refresh_cancellation,
    task_rows,
)
from tests.integration.customer_support import cleanup_customer_db, prepare_customer_db
from tests.integration.db_utils import db_available
from tests.integration.order_query_support import login

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")

TENANT = "tenant-a"


@pytest.fixture(autouse=True)
def demo_customers() -> Any:
    prepare_customer_db()
    yield
    cleanup_customer_db()


def _session_cookie(app: Any) -> tuple[str, dict[str, Any]]:
    """登录一次并返回 cookie 与已建任务；并发用例共享同一 session，避免登录轮换。"""
    with api_client(app) as api:
        login(api)
        created = create_cancellation(api).json()
        token = api.cookies.get("csid")
    assert token
    return token, created


def test_唯一索引冲突回读已有任务_AC_66(monkeypatch: pytest.MonkeyPatch) -> None:
    """前置查询漏掉并发任务时，唯一索引兜底并回读，不新建也不报 500。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        first = create_cancellation(api)
        original = customer_cancellations._in_progress_task
        calls = {"count": 0}

        async def racing_precheck(*args: Any, **kwargs: Any) -> Any:
            calls["count"] += 1
            if calls["count"] == 1:
                # 模拟并发方已插入但尚未提交：前置查询看不见。
                return None
            return await original(*args, **kwargs)

        monkeypatch.setattr(customer_cancellations, "_in_progress_task", racing_precheck)
        second = create_cancellation(api)

    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert calls["count"] == 2
    assert len(task_rows()) == 1
    assert app.state.oms.calls["submit_cancel"] == 0


def test_重复确认只提交一次并返回同一结果_AC_66() -> None:
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        created = create_cancellation(api).json()
        first = confirm_cancellation(api, created["id"])
        second = confirm_cancellation(api, created["id"])

    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["state"] == second.json()["state"] == "ACCEPTED"
    assert first.json()["confirmed_at"] == second.json()["confirmed_at"]
    assert app.state.oms.calls["submit_cancel"] == 1

    [row] = task_rows()
    assert row.state == "ACCEPTED"
    assert row.version >= 2


def test_并发确认只有一个推进_AC_66() -> None:
    token, created = _session_cookie(default_order_app())
    task_id = created["id"]
    barrier = threading.Barrier(2)

    def attempt() -> tuple[int, dict[str, Any], int]:
        app = default_order_app()
        with TestClient(app) as client:
            client.cookies.set("csid", token)
            barrier.wait(timeout=10)
            response = confirm_cancellation(client, task_id)
            return response.status_code, response.json(), app.state.oms.calls["submit_cancel"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))

    statuses = sorted(status for status, _, _ in results)
    # 一个推进，另一个幂等返回或 409；不允许两个都触发提交。
    assert statuses in ([200, 200], [200, 409]), results
    assert sum(submits for _, _, submits in results) == 1
    for status, body, _ in results:
        if status == 200:
            assert body["state"] == "ACCEPTED", body
        else:
            assert body["code"] == "CANCELLATION_CONFLICT", body

    [row] = task_rows()
    assert row.state == "ACCEPTED"
    assert row.confirmed_at is not None


def test_同一订单重复发起复用当前任务_AC_66() -> None:
    """等待确认与已受理阶段都不新建任务，也不触发第二次提交。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        first = create_cancellation(api).json()
        waiting = create_cancellation(api).json()
        confirm_cancellation(api, first["id"])
        accepted = create_cancellation(api).json()

    assert first["id"] == waiting["id"] == accepted["id"]
    assert accepted["state"] == "ACCEPTED"
    assert len(task_rows()) == 1
    assert app.state.oms.calls["submit_cancel"] == 1


def test_终态后再次发起按新请求走资格判定_AC_66() -> None:
    """旧任务保持 CANCELLED，不重新提交；新请求被已取消订单直接拒绝。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        created = create_cancellation(api).json()
        confirm_cancellation(api, created["id"])
        [row] = task_rows()
        app.state.oms.set_cancel_result(TENANT, row.idempotency_key, "CANCELLED")
        refreshed = refresh_cancellation(api, created["id"])
        again = create_cancellation(api)

    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["state"] == "CANCELLED"
    assert again.status_code == 200, again.text
    body = again.json()
    assert body["id"] != created["id"]
    assert body["state"] == "ELIGIBILITY_REJECTED"
    assert body["reason_text"] == "订单已取消"
    assert body["can_confirm"] is False

    rows = {row.id: row for row in task_rows()}
    assert rows[created["id"]].state == "CANCELLED"
    assert rows[body["id"]].state == "ELIGIBILITY_REJECTED"
    assert app.state.oms.calls["submit_cancel"] == 1


def test_并发发起同一订单只建一个任务_AC_66() -> None:
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        token = api.cookies.get("csid")
    assert token
    barrier = threading.Barrier(2)

    def attempt() -> tuple[int, dict[str, Any], int]:
        app = default_order_app()
        with TestClient(app) as client:
            client.cookies.set("csid", token)
            barrier.wait(timeout=10)
            response = create_cancellation(client)
            return response.status_code, response.json(), app.state.oms.calls["submit_cancel"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))

    rows = task_rows()
    assert len(rows) == 1
    assert sum(submits for _, _, submits in results) == 0
    statuses = sorted(status for status, _, _ in results)
    assert statuses in ([200, 200], [200, 409]), results
    bodies = [body for _, body, _ in results if "id" in body]
    if len(bodies) == 2:
        assert bodies[0]["id"] == bodies[1]["id"]
    assert rows[0].state == "AWAITING_CONFIRMATION"
