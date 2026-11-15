"""会话建立、切换、退出与未认证拦截（AC-20、AC-02、AC-03、AC-15）。"""

from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from services.api.auth import Identity, current_identity, reset_sessions
from services.api.main import create_app


def client() -> TestClient:
    reset_sessions()
    return TestClient(create_app())


def test_选择测试账号建立会话_AC_20() -> None:
    with client() as api:
        response = api.post("/session", json={"account_id": "zhang-ming"})
        assert response.status_code == 200
        body = response.json()
        assert body["tenant_id"] == "tenant-a"
        assert body["user_id"] == "user-a1"
        assert api.cookies.get("sid")


def test_未登录访问会话接口返回401_AC_20() -> None:
    with client() as api:
        assert api.get("/session").status_code == 401


def test_切换账号后身份随之变化_AC_20() -> None:
    with client() as api:
        api.post("/session", json={"account_id": "zhang-ming"})
        response = api.post("/session", json={"account_id": "wang-qiang"})
        assert response.json()["tenant_id"] == "tenant-b"
        assert api.get("/session").json()["user_id"] == "user-b1"


def test_退出后会话失效_AC_20() -> None:
    with client() as api:
        api.post("/session", json={"account_id": "zhang-ming"})
        assert api.delete("/session").status_code == 204
        assert api.get("/session").status_code == 401


def test_未知账号被拒绝_AC_20() -> None:
    with client() as api:
        assert api.post("/session", json={"account_id": "nobody"}).status_code == 404


def test_请求体不得覆盖租户或用户_AC_02() -> None:
    with client() as api:
        response = api.post(
            "/session",
            json={"account_id": "zhang-ming", "tenant_id": "tenant-b", "user_id": "user-b1"},
        )
        assert response.status_code == 422


def test_受保护路由无会话返回401_AC_03() -> None:
    reset_sessions()
    app = FastAPI()

    @app.get("/protected")
    def protected(
        identity: Annotated[Identity, Depends(current_identity)],
    ) -> dict[str, str]:
        return {"tenant_id": identity.tenant_id}

    with TestClient(app) as api:
        assert api.get("/protected").status_code == 401
