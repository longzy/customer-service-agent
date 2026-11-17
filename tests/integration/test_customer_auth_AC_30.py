"""F-01：客户登录、会话恢复、登出与跨客户 404（AC-30）。

集成测试跑在独立测试库；所有断言都通过真实 HTTP 路由与数据库完成。
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.api.main import create_app
from backend.identity.customer_sessions import (
    CUSTOMER_COOKIE,
    CUSTOMER_SESSION_TTL,
    hash_token,
)
from backend.identity.passwords import hash_password
from backend.platform.db import get_session
from backend.platform.models import (
    ServiceConversation,
    ServiceCustomer,
    ServiceCustomerSession,
    ServiceRateLimitBucket,
)
from backend.platform.settings import Settings, settings
from tests.integration.db_utils import db_available

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")

DEMO_CREDENTIAL = "demo-login-value"
CUSTOMER_A = ("customer_a", "客户甲")
CUSTOMER_B = ("customer_b", "客户乙")


async def _with_db(action: Any) -> Any:
    """每次开独立 engine，避免 TestClient 与测试库操作跨事件循环复用连接池。"""
    engine = create_async_engine(settings.database_url)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as db:
            return await action(db)
    finally:
        await engine.dispose()


async def _reset(db: Any) -> None:
    await db.execute(delete(ServiceCustomerSession))
    await db.execute(delete(ServiceConversation))
    await db.execute(delete(ServiceCustomer))
    await db.execute(delete(ServiceRateLimitBucket))
    await db.commit()


async def _seed(db: Any) -> None:
    for username, display_name in (CUSTOMER_A, CUSTOMER_B):
        db.add(
            ServiceCustomer(
                id=f"cust-{username}",
                tenant_id=settings.m1_tenant_id,
                username=username,
                password_hash=hash_password(DEMO_CREDENTIAL),
                display_name=display_name,
                active=True,
            )
        )
    await db.commit()


@pytest.fixture(autouse=True)
def demo_customers() -> Any:
    asyncio.run(_with_db(_reset))
    asyncio.run(_with_db(_seed))
    yield
    asyncio.run(_with_db(_reset))


def api_client(active: Settings | None = None) -> TestClient:
    return TestClient(create_app(active))


def login(api: TestClient, username: str = "customer_a") -> Any:
    response = api.post(
        "/customer/sessions",
        json={"username": username, "password": DEMO_CREDENTIAL},
    )
    assert response.status_code == 200, response.text
    return response


def session_rows() -> list[ServiceCustomerSession]:
    async def read(db: Any) -> list[ServiceCustomerSession]:
        return list((await db.execute(select(ServiceCustomerSession))).scalars())

    return asyncio.run(_with_db(read))


def conversation_rows() -> list[ServiceConversation]:
    async def read(db: Any) -> list[ServiceConversation]:
        return list((await db.execute(select(ServiceConversation))).scalars())

    return asyncio.run(_with_db(read))


def test_登录成功返回会话并设置安全Cookie_AC_30() -> None:
    with api_client() as api:
        response = login(api)
        body = response.json()

    assert body["customer"]["username"] == "customer_a"
    assert body["customer"]["display_name"] == "客户甲"
    assert body["conversation"]["status"] == "AI_ACTIVE"
    assert body["conversation"]["after_id"] == 0
    assert body["conversation"]["id"]

    header = response.headers["set-cookie"]
    jar = SimpleCookie()
    jar.load(header)
    cookie = jar[CUSTOMER_COOKIE]
    assert cookie["httponly"] is True
    assert cookie["samesite"] == "lax"
    assert cookie["max-age"] == str(int(CUSTOMER_SESSION_TTL.total_seconds()))
    assert cookie["path"] == "/"
    assert not cookie["secure"]

    token = cookie.value
    rows = session_rows()
    assert len(rows) == 1
    assert rows[0].token_hash == hash_token(token)
    assert token not in rows[0].token_hash
    assert len(rows[0].token_hash) == 64


def test_刷新与重新登录恢复同一未关闭会话_旧token失效_AC_30() -> None:
    with api_client() as api:
        first = login(api)
        conversation_id = first.json()["conversation"]["id"]
        first_token = api.cookies.get(CUSTOMER_COOKIE)

        restored = api.get("/customer/session")
        assert restored.status_code == 200
        assert restored.json()["conversation"]["id"] == conversation_id

        second = login(api)
        assert second.json()["conversation"]["id"] == conversation_id
        second_token = api.cookies.get(CUSTOMER_COOKIE)
        assert second_token != first_token

        api.cookies.clear()
        api.cookies.set(CUSTOMER_COOKIE, first_token)
        stale = api.get("/customer/session")
        assert stale.status_code == 401
        assert stale.json()["code"] == "SESSION_INVALID"

        api.cookies.clear()
        api.cookies.set(CUSTOMER_COOKIE, second_token)
        assert api.get("/customer/session").status_code == 200

    active = [row for row in session_rows() if row.revoked_at is None]
    assert len(active) == 1
    assert active[0].token_hash == hash_token(second_token)
    assert len(conversation_rows()) == 1
    assert conversation_rows()[0].id == conversation_id


def test_登出撤销session且旧cookie再访问401_AC_30() -> None:
    with api_client() as api:
        login(api)
        token = api.cookies.get(CUSTOMER_COOKIE)
        response = api.delete("/customer/sessions")
        assert response.status_code == 204
        assert response.headers["set-cookie"].startswith(f'{CUSTOMER_COOKIE}="";')

        api.cookies.clear()
        api.cookies.set(CUSTOMER_COOKIE, token)
        after = api.get("/customer/session")
        assert after.status_code == 401
        assert after.json()["code"] == "SESSION_INVALID"

    assert all(row.revoked_at is not None for row in session_rows())


def test_错误密码与未知账号统一401_空字段422_AC_30() -> None:
    with api_client() as api:
        wrong = api.post(
            "/customer/sessions",
            json={"username": "customer_a", "password": "wrong-value"},
        )
        unknown = api.post(
            "/customer/sessions",
            json={"username": "nobody", "password": "wrong-value"},
        )
        empty = api.post("/customer/sessions", json={"username": "customer_a", "password": ""})
        extra = api.post(
            "/customer/sessions",
            json={"username": "customer_a", "password": DEMO_CREDENTIAL, "tenant_id": "tenant-b"},
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


def test_跨客户读取会话返回404_AC_30() -> None:
    with api_client() as api:
        conversation_id = login(api, "customer_a").json()["conversation"]["id"]
        own = api.get(f"/customer/conversations/{conversation_id}")
        assert own.status_code == 200

        body = login(api, "customer_b").json()
        assert body["conversation"]["id"] != conversation_id
        cross = api.get(f"/customer/conversations/{conversation_id}")
        missing = api.get("/customer/conversations/does-not-exist")

    assert cross.status_code == 404
    assert cross.json()["code"] == "NOT_FOUND"
    assert missing.status_code == 404
    assert missing.json() == cross.json()


def test_未登录访问客户资源返回401_登出幂等_AC_30() -> None:
    with api_client() as api:
        assert api.get("/customer/session").status_code == 401
        assert api.get("/customer/conversations/anything").status_code == 401
        assert api.get("/customer/session").json()["code"] == "SESSION_INVALID"
        assert api.delete("/customer/sessions").status_code == 204


def test_登录连续失败超限返回429_AC_30() -> None:
    with api_client() as api:
        statuses = [
            api.post(
                "/customer/sessions",
                json={"username": "customer_a", "password": f"wrong-{index}"},
            ).status_code
            for index in range(6)
        ]
        limited = api.post(
            "/customer/sessions",
            json={"username": "customer_a", "password": DEMO_CREDENTIAL},
        )
        assert statuses[:5] == [401] * 5
        assert statuses[5] == 429
        assert limited.status_code == 429
        assert limited.json()["code"] == "RATE_LIMITED"
        assert limited.json()["message"] == "请求过于频繁，请稍后再试"
        assert int(limited.headers["Retry-After"]) > 0


def test_生产环境Cookie默认Secure_AC_30() -> None:
    active = Settings(
        environment="production",
        m1_enabled=True,
        database_url=settings.database_url,
        oms_base_url="https://oms.example.com",
        model_api_key="test-key",
    )
    with api_client(active) as api:
        response = login(api)
    jar = SimpleCookie()
    jar.load(response.headers["set-cookie"])
    assert jar[CUSTOMER_COOKIE]["secure"] is True


def test_24h绝对过期不因刷新滑动_AC_30(monkeypatch: pytest.MonkeyPatch) -> None:
    base = datetime(2026, 11, 17, 3, 0, 0, tzinfo=UTC)
    monkeypatch.setattr("backend.identity.customer_sessions.utc_now", lambda: base)
    with api_client() as api:
        response = login(api)
        assert response.json()["expires_at"] == "2026-11-18T03:00:00Z"

        monkeypatch.setattr(
            "backend.identity.customer_sessions.utc_now",
            lambda: base + timedelta(hours=23),
        )
        assert api.get("/customer/session").status_code == 200

        monkeypatch.setattr(
            "backend.identity.customer_sessions.utc_now",
            lambda: base + timedelta(hours=24, seconds=1),
        )
        expired = api.get("/customer/session")
    assert expired.status_code == 401
    assert expired.json()["code"] == "SESSION_EXPIRED"


def test_依赖故障返回5xx封套_AC_30() -> None:
    app = create_app()

    async def broken_db() -> Any:
        raise RuntimeError("database down")

    app.dependency_overrides[get_session] = broken_db
    with TestClient(app, raise_server_exceptions=False) as api:
        response = api.post(
            "/customer/sessions",
            json={"username": "customer_a", "password": DEMO_CREDENTIAL},
            headers={"X-Request-ID": "trace-5xx"},
        )
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert response.json()["visible"] is False
    assert response.headers["X-Request-ID"] == "trace-5xx"


def test_请求关联标识透传或生成_基座豁免() -> None:
    with api_client() as api:
        passed = api.get("/health", headers={"X-Request-ID": "trace-abc_1"})
        generated = api.get("/health")
    assert passed.headers["X-Request-ID"] == "trace-abc_1"
    assert uuid.UUID(generated.headers["X-Request-ID"])


def test_旧路由422响应格式不被新封套改写_基座豁免() -> None:
    with api_client() as api:
        response = api.post(
            "/session",
            json={"account_id": "zhang-ming", "tenant_id": "tenant-b"},
        )
    assert response.status_code == 422
    assert "detail" in response.json()
    assert "code" not in response.json()


def test_M1关闭时客户路由不挂载_AC_30() -> None:
    active = Settings(environment="development", m1_enabled=False)
    with api_client(active) as api:
        response = api.post(
            "/customer/sessions",
            json={"username": "customer_a", "password": DEMO_CREDENTIAL},
        )
    assert response.status_code == 404
