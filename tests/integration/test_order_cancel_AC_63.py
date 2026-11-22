"""F-32：聊天取消入口、会话内定位与固定短语确认（AC-63）。

自然语言取消进入取消分支并出确认卡片；会话内最近一次成功查询恰好一笔时直接
定位；没带订单号或多单时列候选、不替客户选；订单号作兜底精确定位；固定短语由
服务端确定性确认；人工接管期间不触发 AI 自动取消。
"""

from typing import Any

import pytest

from backend.adapters.oms.faults import FaultRule
from tests.integration.cancellation_support import (
    api_client,
    default_order_app,
    task_rows,
)
from tests.integration.customer_support import cleanup_customer_db, prepare_customer_db
from tests.integration.db_utils import db_available
from tests.integration.order_query_support import (
    ai_messages,
    bind_customer,
    login,
    send,
)

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")

CONFIRM_PHRASES = ("确认取消", "确定取消", "是的，取消")


@pytest.fixture(autouse=True)
def demo_customers() -> Any:
    prepare_customer_db()
    yield
    cleanup_customer_db()


def _last_ai(body: dict[str, Any]) -> dict[str, Any]:
    return ai_messages(body)[-1]


def _query_one(api: Any, order_id: str = "ORD-10001") -> dict[str, Any]:
    """先做一次单笔查询，制造“会话内最近一次成功查询恰好一笔”的快照。"""
    queried = send(api, f"查一下 {order_id}")
    assert queried.status_code == 200, queried.text
    return queried.json()


def test_取消订单进入取消分支并出确认卡片_AC_63() -> None:
    """会话内快照恰好一笔：自然语言取消直接出确认卡片，停在等待确认且不写 OMS。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        _query_one(api)
        response = send(api, "取消订单")

    assert response.status_code == 200, response.text
    message = _last_ai(response.json())
    payload = message["payload"]
    assert [order["order_id"] for order in payload["orders"]] == ["ORD-10001"]
    cancellation = payload["cancellation"]
    assert cancellation["state"] == "AWAITING_CONFIRMATION"
    assert cancellation["can_confirm"] is True
    assert cancellation["expires_at"].endswith("Z")
    assert "确认取消" in message["content"]
    assert "尚未提交" in message["content"]

    [row] = task_rows()
    assert row.order_id == "ORD-10001"
    assert row.state == "AWAITING_CONFIRMATION"
    assert app.state.oms.calls["submit_cancel"] == 0


@pytest.mark.parametrize("content", ["这单不要了", "取消这单"])
def test_自然语言取消表达同样进入取消分支_AC_63(content: str) -> None:
    """“这单不要了/取消这单”与“取消订单”同一条确定性取消分支。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        _query_one(api)
        response = send(api, content)

    assert response.status_code == 200, response.text
    message = _last_ai(response.json())
    assert message["payload"]["cancellation"]["state"] == "AWAITING_CONFIRMATION"
    assert message["payload"]["orders"][0]["order_id"] == "ORD-10001"
    assert app.state.oms.calls["submit_cancel"] == 0


def test_带订单号精确定位_AC_63() -> None:
    """订单号是兜底：没有会话快照也能精确定位并出卡片。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        response = send(api, "取消 ORD-10001")

    assert response.status_code == 200, response.text
    message = _last_ai(response.json())
    assert message["payload"]["orders"][0]["order_id"] == "ORD-10001"
    assert message["payload"]["cancellation"]["state"] == "AWAITING_CONFIRMATION"
    [row] = task_rows()
    assert row.order_id == "ORD-10001"


def test_无快照多单列候选不建任务_AC_63() -> None:
    """没带订单号且名下多单：列最近订单候选，不替客户选、不建任务。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        response = send(api, "取消订单")

    assert response.status_code == 200, response.text
    message = _last_ai(response.json())
    payload = message["payload"]
    assert len(payload["orders"]) > 1
    assert payload.get("cancellation") is None
    assert "不能替你选" in message["content"]
    assert task_rows() == []
    assert app.state.oms.calls["submit_cancel"] == 0


def test_无快照恰好一笔时列候选_AC_63() -> None:
    """没带订单号且没有会话快照：即使名下恰好一笔也列候选，由客户自己点选。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        # 客户甲的 OMS 身份改为只有一笔订单（ORD-10005）的客户。
        bind_customer("customer_a", "user-a2")
        response = send(api, "取消订单")

    assert response.status_code == 200, response.text
    message = _last_ai(response.json())
    assert [order["order_id"] for order in message["payload"]["orders"]] == ["ORD-10005"]
    assert not message["payload"].get("cancellation")
    assert "不能替你选" in message["content"]
    assert task_rows() == []


def test_他人订单号统一查无_AC_63() -> None:
    """他人/不存在订单统一查无，不建任务、不调用 OMS 写接口。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        response = send(api, "取消 ORD-10005")

    assert response.status_code == 200, response.text
    message = _last_ai(response.json())
    assert "没有查到你名下" in message["content"]
    assert task_rows() == []
    assert app.state.oms.calls["submit_cancel"] == 0


def test_已发货订单不可取消且不写oms_AC_63() -> None:
    """资格拒绝：确认卡片展示原因且不可提交，OMS 写调用为 0。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        response = send(api, "取消 ORD-10003")

    assert response.status_code == 200, response.text
    message = _last_ai(response.json())
    cancellation = message["payload"]["cancellation"]
    assert cancellation["state"] == "ELIGIBILITY_REJECTED"
    assert cancellation["can_confirm"] is False
    assert "已发货" in message["content"]
    [row] = task_rows()
    assert row.state == "ELIGIBILITY_REJECTED"
    assert app.state.oms.calls["submit_cancel"] == 0


def test_固定短语确认只提交一次_AC_63() -> None:
    """“确认取消”命中待确认任务后由服务端确认，来源 PHRASE，只提交一次。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        _query_one(api)
        created = _last_ai(send(api, "取消订单").json())
        assert created["payload"]["cancellation"]["can_confirm"] is True
        response = send(api, "确认取消")

    assert response.status_code == 200, response.text
    message = _last_ai(response.json())
    assert message["payload"]["cancellation"]["state"] == "ACCEPTED"
    assert "已受理" in message["content"]
    assert "已取消" not in message["content"]
    assert "退款" not in message["content"]
    [row] = task_rows()
    assert row.state == "ACCEPTED"
    assert row.confirmation_source == "PHRASE"
    assert app.state.oms.calls["submit_cancel"] == 1


@pytest.mark.parametrize("phrase", CONFIRM_PHRASES)
def test_确认短语集合都能提交_AC_63(phrase: str) -> None:
    """三个已定短语（确认取消/确定取消/是的，取消）都能完成确认。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        _query_one(api)
        send(api, "取消订单")
        response = send(api, phrase)

    assert response.status_code == 200, response.text
    assert _last_ai(response.json())["payload"]["cancellation"]["state"] == "ACCEPTED"
    assert app.state.oms.calls["submit_cancel"] == 1


def test_无待确认任务时发确认短语不提交_AC_63() -> None:
    """没有待确认任务时发“确认取消”：只提示，不建任务、不写 OMS。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        response = send(api, "确认取消")

    assert response.status_code == 200, response.text
    message = _last_ai(response.json())
    assert "没有待确认" in message["content"]
    assert task_rows() == []
    assert app.state.oms.calls["submit_cancel"] == 0


def test_退款仍转人工不进取消分支_AC_63() -> None:
    """退款等仍按 001/003 的超范围路径转人工，不创建取消任务。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        response = send(api, "我要退款")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "QUEUED"
    assert task_rows() == []
    assert app.state.oms.calls["submit_cancel"] == 0


def test_人工接管期间不触发AI自动取消_AC_63() -> None:
    """排队/人工期间客户消息只落库，不触发 AI 自动取消、不建任务。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        queued = send(api, "转人工")
        assert queued.json()["status"] == "QUEUED"
        response = send(api, "取消这单")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "QUEUED"
    assert [item["author_type"] for item in body["messages"]] == ["customer"]
    assert task_rows() == []
    assert app.state.oms.calls["submit_cancel"] == 0


def test_重放不重复创建任务_AC_63() -> None:
    """同一幂等键重放返回原消息，不重复创建任务或确认卡片。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        _query_one(api)
        first = send(api, "取消订单", key="cancel-replay-1")
        second = send(api, "取消订单", key="cancel-replay-1")

    assert first.status_code == second.status_code == 200
    assert len(ai_messages(second.json())) == len(ai_messages(first.json()))
    assert len(task_rows()) == 1
    assert app.state.oms.calls["submit_cancel"] == 0


def test_取消定位查询失败提示可重试_AC_63() -> None:
    """定位查询失败按订单失败分级提示重试，不建任务、不写 OMS。"""
    app = default_order_app()
    app.state.oms.faults.add(FaultRule(kind="timeout", tool="list_recent_orders", times=1))
    with api_client(app) as api:
        login(api)
        response = send(api, "取消订单")

    assert response.status_code == 200, response.text
    message = _last_ai(response.json())
    assert "暂时不可用" in message["content"]
    assert task_rows() == []
    assert app.state.oms.calls["submit_cancel"] == 0
