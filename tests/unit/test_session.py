"""会话建立、切换、退出与未认证拦截（AC-20）。"""

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app


def client() -> TestClient:
    return TestClient(create_app())


def client_with_sid(sid: str) -> TestClient:
    api = TestClient(create_app())
    api.cookies.set("sid", sid)
    return api


def test_选择测试账号建立会话_AC_20() -> None:
    with client() as api:
        response = api.post("/session", json={"account_id": "zhang-ming"})
        assert response.status_code == 200
        body = response.json()
        assert body["tenant_id"] == "tenant-a"
        assert body["user_id"] == "user-a1"
        assert api.cookies.get("sid")
        cookie = response.headers["set-cookie"].lower()
        assert "httponly" in cookie
        assert "samesite=lax" in cookie
        assert "max-age=28800" in cookie
        assert "secure" not in cookie


def test_未登录访问会话接口返回401_AC_20() -> None:
    with client() as api:
        assert api.get("/session").status_code == 401


def test_切换账号后身份随之变化_AC_20() -> None:
    with client() as api:
        first = api.post("/session", json={"account_id": "zhang-ming"})
        old_sid = first.cookies.get("sid") or api.cookies.get("sid")
        response = api.post("/session", json={"account_id": "wang-qiang"})
        assert response.json()["tenant_id"] == "tenant-b"
        assert api.get("/session").json()["user_id"] == "user-b1"
        with client_with_sid(old_sid) as stale:
            assert stale.get("/session").status_code == 401, "切换账号后旧会话必须失效"


def test_退出后会话失效_AC_20() -> None:
    with client() as api:
        login = api.post("/session", json={"account_id": "zhang-ming"})
        sid = login.cookies.get("sid") or api.cookies.get("sid")
        assert api.delete("/session").status_code == 204
        assert api.get("/session").status_code == 401
        with client_with_sid(sid) as stale:
            assert stale.get("/session").status_code == 401, "服务端会话必须失效"


@pytest.mark.parametrize(
    ("account_id", "tenant_id", "user_id"),
    [
        ("zhang-ming", "tenant-a", "user-a1"),
        ("li-hua", "tenant-a", "user-a2"),
        ("wang-qiang", "tenant-b", "user-b1"),
        ("zhao-min", "tenant-b", "user-b2"),
    ],
)
def test_四个测试账号都能登录_AC_20(account_id: str, tenant_id: str, user_id: str) -> None:
    with client() as api:
        body = api.post("/session", json={"account_id": account_id}).json()
        assert (body["tenant_id"], body["user_id"]) == (tenant_id, user_id)


def test_同租户内切换账号_AC_20() -> None:
    with client() as api:
        api.post("/session", json={"account_id": "zhang-ming"})
        body = api.post("/session", json={"account_id": "li-hua"}).json()
        assert (body["tenant_id"], body["user_id"]) == ("tenant-a", "user-a2")


def test_会话过期后失效_AC_20(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import timedelta

    from services import identity as auth

    monkeypatch.setattr(auth, "SESSION_TTL", timedelta(seconds=-1))
    with client() as api:
        login = api.post("/session", json={"account_id": "zhang-ming"})
        sid = login.cookies.get("sid") or api.cookies.get("sid")
        with client_with_sid(sid) as stale:
            assert stale.get("/session").status_code == 401


def test_未知账号被拒绝_AC_20() -> None:
    with client() as api:
        assert api.post("/session", json={"account_id": "nobody"}).status_code == 404


def test_请求体不得覆盖租户或用户_AC_20() -> None:
    with client() as api:
        response = api.post(
            "/session",
            json={"account_id": "zhang-ming", "tenant_id": "tenant-b", "user_id": "user-b1"},
        )
        assert response.status_code == 422


def test_中间件未认证时返回401_AC_20() -> None:
    with client() as api:
        assert api.get("/session").status_code == 401
        assert "location" not in {key.lower() for key in api.get("/session").headers}
