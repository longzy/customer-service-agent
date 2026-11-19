"""全局会话安全基线：跨站写请求与 Cookie Secure 配置。

写请求统一走当前客户登录入口；空请求体只会触发校验，不触碰数据库。
Cookie 属性由 AC-30/AC-34 覆盖，这里只验证全局 Origin 中间件与配置推导。
"""

import pytest
from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.platform.settings import Settings, settings


def client() -> TestClient:
    return TestClient(create_app())


def write(api: TestClient, origin: str | None = None):
    headers = {"Origin": origin} if origin is not None else {}
    return api.post("/customer/sessions", json={}, headers=headers)


def test_同源写请求不被拦截_基座豁免() -> None:
    with client() as api:
        assert write(api, "http://testserver").status_code != 403


def test_缺Origin的写请求不被拦截_基座豁免() -> None:
    """命令行与内部调用没有 Origin；浏览器跨站写请求一定会带。"""
    with client() as api:
        assert write(api).status_code != 403


def test_跨源写请求被拒绝_基座豁免() -> None:
    with client() as api:
        response = write(api, "http://evil.example")
        assert response.status_code == 403
        assert "set-cookie" not in response.headers


def test_本地前端代理来源不被拦截_基座豁免() -> None:
    """Next 开发服务器把 /api 代理到后端：Origin 是 3000，Host 是 8000。"""
    with TestClient(create_app(), base_url="http://127.0.0.1:8000") as api:
        response = write(api, "http://localhost:3000")
        assert response.status_code != 403


def test_不透明来源被拒绝_基座豁免() -> None:
    with client() as api:
        assert write(api, "null").status_code == 403


def test_白名单来源不被拦截_基座豁免(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "allowed_origins", "http://app.example")
    with client() as api:
        assert write(api, "http://app.example").status_code != 403


def test_跨源读请求不受影响_基座豁免() -> None:
    with client() as api:
        response = api.get("/health", headers={"Origin": "http://evil.example"})
        assert response.status_code == 200


def test_生产环境默认要求Secure_基座豁免() -> None:
    assert Settings(environment="production", _env_file=None).secure_cookie is True
    assert Settings(environment="development", _env_file=None).secure_cookie is False
    assert Settings(environment="test", _env_file=None).secure_cookie is False


def test_空COOKIE_SECURE按未设置处理_基座豁免() -> None:
    """照抄 .env.example 的 `COOKIE_SECURE=` 不能让服务起不来。"""
    assert (
        Settings(environment="development", cookie_secure="", _env_file=None).secure_cookie is False
    )
