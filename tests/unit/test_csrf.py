"""会话安全基线：Cookie 属性与跨站写请求（AC-21）。"""

import pytest
from fastapi.testclient import TestClient

from services import identity as auth
from services.api.main import create_app
from services.platform.settings import Settings, settings


def client() -> TestClient:
    return TestClient(create_app())


def login(api: TestClient, origin: str | None = None):
    headers = {"Origin": origin} if origin is not None else {}
    return api.post("/session", json={"account_id": "zhang-ming"}, headers=headers)


def test_同源写请求通过_AC_21() -> None:
    with client() as api:
        assert login(api, "http://testserver").status_code == 200


def test_缺Origin的写请求通过_AC_21() -> None:
    """命令行与内部调用没有 Origin；浏览器跨站写请求一定会带。"""
    with client() as api:
        assert login(api).status_code == 200


def test_跨源写请求被拒绝且无副作用_AC_21() -> None:
    with client() as api:
        before = len(auth._sessions)
        response = login(api, "http://evil.example")
        assert response.status_code == 403
        assert "set-cookie" not in response.headers
        assert len(auth._sessions) == before
        assert api.get("/session").status_code == 401


def test_本地前端代理来源通过_AC_21() -> None:
    """Next 开发服务器把 /api 代理到后端：Origin 是 3000，Host 是 8000。"""
    with TestClient(create_app(), base_url="http://127.0.0.1:8000") as api:
        response = api.post(
            "/session",
            json={"account_id": "zhang-ming"},
            headers={"Origin": "http://localhost:3000"},
        )
        assert response.status_code == 200


def test_不透明来源被拒绝_AC_21() -> None:
    with client() as api:
        assert login(api, "null").status_code == 403


def test_白名单来源通过_AC_21(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "allowed_origins", "http://app.example")
    with client() as api:
        assert login(api, "http://app.example").status_code == 200


def test_跨源读请求不受影响_AC_21() -> None:
    with client() as api:
        response = api.get("/health", headers={"Origin": "http://evil.example"})
        assert response.status_code == 200


def test_开发环境Cookie不带Secure_AC_21() -> None:
    with client() as api:
        cookie = login(api).headers["set-cookie"].lower()
        assert "httponly" in cookie
        assert "samesite=lax" in cookie
        assert "secure" not in cookie


def test_安全模式Cookie带Secure_AC_21(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "cookie_secure", True)
    with client() as api:
        assert "secure" in login(api).headers["set-cookie"].lower()


def test_生产环境默认要求Secure_AC_21() -> None:
    assert Settings(environment="production", _env_file=None).secure_cookie is True
    assert Settings(environment="development", _env_file=None).secure_cookie is False
    assert Settings(environment="test", _env_file=None).secure_cookie is False


def test_空COOKIE_SECURE按未设置处理_AC_21() -> None:
    """照抄 .env.example 的 `COOKIE_SECURE=` 不能让服务起不来。"""
    assert (
        Settings(environment="development", cookie_secure="", _env_file=None).secure_cookie is False
    )


def test_生产环境真实响应头带Secure_AC_21(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(Settings, "test_accounts_enabled", property(lambda self: True))
    with client() as api:
        cookie = login(api).headers["set-cookie"].lower()
        assert "secure" in cookie
