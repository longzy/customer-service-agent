"""F-05：坐席登录、8h session、RBAC 与越权 404（AC-34）。

集成测试跑在独立测试库；所有断言都通过真实 HTTP 路由与数据库完成。
"""

from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.identity.employee_sessions import (
    EMPLOYEE_COOKIE,
    EMPLOYEE_SESSION_TTL,
    hash_token,
)
from backend.platform.models import ServiceEmployeeSession
from backend.platform.settings import Settings, settings
from tests.integration.db_utils import db_available
from tests.integration.workspace_support import (
    DEMO_CREDENTIAL,
    cleanup_workspace_db,
    login_employee,
    prepare_workspace_db,
    rows_of,
    seed_conversation,
    set_employee_role,
)

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")


@pytest.fixture(autouse=True)
def workspace_data() -> Any:
    prepare_workspace_db()
    yield
    cleanup_workspace_db()


def api_client(active: Settings | None = None) -> TestClient:
    return TestClient(create_app(active))


def session_rows() -> list[ServiceEmployeeSession]:
    return rows_of(ServiceEmployeeSession)


def test_坐席登录成功返回员工并设置8h安全Cookie_AC_34() -> None:
    with api_client() as api:
        response = login_employee(api, "agent_1")

    body = response.json()
    assert body["employee"]["username"] == "agent_1"
    assert body["employee"]["display_name"] == "坐席 1"
    assert body["employee"]["role"] == "agent"
    assert body["expires_at"]

    jar = SimpleCookie()
    jar.load(response.headers["set-cookie"])
    cookie = jar[EMPLOYEE_COOKIE]
    assert cookie["httponly"] is True
    assert cookie["samesite"] == "lax"
    assert cookie["max-age"] == str(int(EMPLOYEE_SESSION_TTL.total_seconds()))
    assert cookie["path"] == "/"
    assert not cookie["secure"]

    token = cookie.value
    rows = session_rows()
    assert len(rows) == 1
    assert rows[0].token_hash == hash_token(token)
    assert len(rows[0].token_hash) == 64
    assert token not in rows[0].token_hash


def test_cookie不包含客户身份且员工会话独立_AC_34() -> None:
    with api_client() as api:
        login_employee(api)
        assert api.cookies.get(EMPLOYEE_COOKIE)
        assert api.cookies.get("csid") is None
        customer = api.get("/customer/session")
        assert customer.status_code == 401
        assert customer.json()["code"] == "SESSION_INVALID"


def test_刷新与重新登录恢复同一员工_旧token失效_AC_34() -> None:
    with api_client() as api:
        first = login_employee(api)
        employee_id = first.json()["employee"]["id"]
        first_token = api.cookies.get(EMPLOYEE_COOKIE)

        restored = api.get("/workspace/session")
        assert restored.status_code == 200
        assert restored.json()["employee"]["id"] == employee_id

        login_employee(api)
        second_token = api.cookies.get(EMPLOYEE_COOKIE)
        assert second_token != first_token

        api.cookies.clear()
        api.cookies.set(EMPLOYEE_COOKIE, first_token)
        stale = api.get("/workspace/session")
        assert stale.status_code == 401
        assert stale.json()["code"] == "SESSION_INVALID"

        api.cookies.clear()
        api.cookies.set(EMPLOYEE_COOKIE, second_token)
        assert api.get("/workspace/session").status_code == 200

    active = [row for row in session_rows() if row.revoked_at is None]
    assert len(active) == 1
    assert active[0].token_hash == hash_token(second_token)


def test_8h绝对过期不因刷新滑动_AC_34(monkeypatch: pytest.MonkeyPatch) -> None:
    base = datetime(2026, 11, 17, 3, 0, 0, tzinfo=UTC)
    monkeypatch.setattr("backend.identity.employee_sessions.utc_now", lambda: base)
    with api_client() as api:
        response = login_employee(api)
        assert response.json()["expires_at"] == "2026-11-17T11:00:00Z"

        monkeypatch.setattr(
            "backend.identity.employee_sessions.utc_now",
            lambda: base + timedelta(hours=7, minutes=59, seconds=59),
        )
        assert api.get("/workspace/session").status_code == 200

        monkeypatch.setattr(
            "backend.identity.employee_sessions.utc_now",
            lambda: base + EMPLOYEE_SESSION_TTL,
        )
        expired = api.get("/workspace/session")
    assert expired.status_code == 401
    assert expired.json()["code"] == "SESSION_EXPIRED"


def test_登出撤销session且幂等_AC_34() -> None:
    with api_client() as api:
        login_employee(api)
        token = api.cookies.get(EMPLOYEE_COOKIE)
        response = api.delete("/workspace/sessions")
        assert response.status_code == 204
        assert response.headers["set-cookie"].startswith(f'{EMPLOYEE_COOKIE}="";')
        assert api.delete("/workspace/sessions").status_code == 204

        api.cookies.clear()
        api.cookies.set(EMPLOYEE_COOKIE, token)
        after = api.get("/workspace/session")
        assert after.status_code == 401
        assert after.json()["code"] == "SESSION_INVALID"

    assert all(row.revoked_at is not None for row in session_rows())


def test_错误密码与未知账号统一401_空字段和越权字段422_AC_34() -> None:
    with api_client() as api:
        wrong = api.post(
            "/workspace/sessions",
            json={"username": "agent_1", "password": "wrong-value"},
        )
        unknown = api.post(
            "/workspace/sessions",
            json={"username": "nobody", "password": "wrong-value"},
        )
        empty = api.post("/workspace/sessions", json={"username": "agent_1", "password": ""})
        extra = api.post(
            "/workspace/sessions",
            json={"username": "agent_1", "password": DEMO_CREDENTIAL, "role": "admin"},
        )

    assert wrong.status_code == 401
    assert unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.json()["code"] == "AUTH_FAILED"
    assert wrong.json()["message"] == "账号或密码不正确"
    assert empty.status_code == 422
    assert empty.json()["code"] == "VALIDATION_ERROR"
    assert extra.status_code == 422
    assert extra.json()["code"] == "VALIDATION_ERROR"


def test_员工登录连续失败超限返回429_AC_34() -> None:
    with api_client() as api:
        statuses = [
            api.post(
                "/workspace/sessions",
                json={"username": "agent_1", "password": f"wrong-{index}"},
            ).status_code
            for index in range(6)
        ]
        limited = api.post(
            "/workspace/sessions",
            json={"username": "agent_1", "password": DEMO_CREDENTIAL},
        )
        assert statuses[:5] == [401] * 5
        assert statuses[5] == 429
        assert limited.status_code == 429
        assert limited.json()["code"] == "RATE_LIMITED"
        assert limited.json()["message"] == "请求过于频繁，请稍后再试"
        assert int(limited.headers["Retry-After"]) > 0
    assert session_rows() == []


def test_非agent账号登录返回403且不建session_AC_34() -> None:
    with api_client() as api:
        forbidden = api.post(
            "/workspace/sessions",
            json={"username": "supervisor_x", "password": DEMO_CREDENTIAL},
        )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "FORBIDDEN"
    assert forbidden.json()["message"] == "无权访问"
    assert session_rows() == []


def test_登录后角色被降级立即403_AC_34() -> None:
    with api_client() as api:
        login_employee(api)
        assert api.get("/workspace/session").status_code == 200
        set_employee_role("agent_1", "supervisor")
        forbidden = api.get("/workspace/session")
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "FORBIDDEN"


def test_未登录访问工作台资源返回401_AC_34() -> None:
    with api_client() as api:
        assert api.get("/workspace/session").status_code == 401
        assert api.get("/workspace/session").json()["code"] == "SESSION_INVALID"
        assert api.get("/workspace/conversations/anything").status_code == 401


def test_生产环境Cookie默认Secure_AC_34() -> None:
    active = Settings(
        environment="production",
        m1_enabled=True,
        database_url=settings.database_url,
        oms_base_url="https://oms.example.com",
        model_api_key="test-key",
    )
    with api_client(active) as api:
        response = login_employee(api)
    jar = SimpleCookie()
    jar.load(response.headers["set-cookie"])
    assert jar[EMPLOYEE_COOKIE]["secure"] is True


def test_M1关闭时工作台路由不挂载_AC_34() -> None:
    active = Settings(environment="development", m1_enabled=False)
    with api_client(active) as api:
        response = api.post(
            "/workspace/sessions",
            json={"username": "agent_1", "password": DEMO_CREDENTIAL},
        )
    assert response.status_code == 404


def test_本人已分配会话可读_未领取和他人会话404_AC_34() -> None:
    seed_conversation("conv-mine", assigned_employee_id="emp-agent_1")
    seed_conversation("conv-unclaimed", customer_id="cust-extra-1")
    seed_conversation(
        "conv-other",
        customer_id="cust-extra-2",
        assigned_employee_id="emp-agent_2",
    )
    seed_conversation(
        "conv-cross-tenant",
        customer_id="cust-extra-3",
        assigned_employee_id="emp-agent_1",
        tenant_id="tenant-b",
    )

    with api_client() as api:
        login_employee(api, "agent_1")
        mine = api.get("/workspace/conversations/conv-mine")
        unclaimed = api.get("/workspace/conversations/conv-unclaimed")
        other = api.get("/workspace/conversations/conv-other")
        cross = api.get("/workspace/conversations/conv-cross-tenant")
        missing = api.get("/workspace/conversations/does-not-exist")

        login_employee(api, "agent_2")
        agents_own = api.get("/workspace/conversations/conv-other")
        agents_mine = api.get("/workspace/conversations/conv-mine")

    assert mine.status_code == 200
    assert mine.json() == {"id": "conv-mine", "status": "CLAIMED"}
    assert unclaimed.status_code == 404
    assert other.status_code == 404
    assert cross.status_code == 404
    assert missing.status_code == 404
    assert unclaimed.json() == other.json() == cross.json() == missing.json()
    assert agents_own.status_code == 200
    assert agents_mine.status_code == 404
