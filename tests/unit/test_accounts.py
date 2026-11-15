"""开发期账号列表接口（AC-20）。"""

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app


def test_账号列表返回四个测试账号_AC_20() -> None:
    with TestClient(create_app()) as api:
        response = api.get("/accounts")
        assert response.status_code == 200
        accounts = response.json()
        assert len(accounts) == 4
        first = accounts[0]
        assert set(first) == {"account_id", "display_name", "tenant_id", "tenant_name"}
        assert "role" not in first


def test_账号列表覆盖两个租户_AC_20() -> None:
    with TestClient(create_app()) as api:
        accounts = api.get("/accounts").json()
        tenants = {account["tenant_id"] for account in accounts}
        assert tenants == {"tenant-a", "tenant-b"}


def test_登录响应包含租户展示名_AC_20() -> None:
    with TestClient(create_app()) as api:
        body = api.post("/session", json={"account_id": "zhang-ming"}).json()
        assert body["tenant_name"] == "示例商户 A"


def test_生产环境不挂载账号接口_基座豁免(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.api.settings import settings

    monkeypatch.setattr(settings, "environment", "production")
    with TestClient(create_app()) as api:
        assert api.get("/accounts").status_code == 404
