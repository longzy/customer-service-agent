"""AC-26：OMS 配置矩阵与生产启动失败。"""

import pytest
from fastapi.testclient import TestClient

from services.adapters.oms.factory import OmsConfigError, build_oms
from services.adapters.oms.http import HttpOmsAdapter
from services.adapters.oms.mock import MockOmsAdapter
from services.api.main import create_app
from services.platform.settings import Settings


def test_production_without_oms_url_fails_AC_26() -> None:
    with pytest.raises(OmsConfigError, match="OMS_BASE_URL"):
        build_oms(Settings(environment="production", oms_base_url=""))


def test_production_with_blank_oms_url_fails_AC_26() -> None:
    with pytest.raises(OmsConfigError, match="OMS_BASE_URL"):
        build_oms(Settings(environment="production", oms_base_url="   "))


@pytest.mark.parametrize(
    "url",
    [
        "ftp://oms.test",
        "http://",
        "oms.test",
        "http://oms.test:bad",
        "http://[::1",
        "http://oms.test:99999",
        "http://oms.test:0",
        "http:// oms.test",
    ],
)
def test_invalid_oms_url_fails_AC_26(url: str) -> None:
    with pytest.raises(OmsConfigError, match="OMS_BASE_URL"):
        build_oms(Settings(environment="production", oms_base_url=url))


def test_development_without_oms_url_uses_mock_AC_26() -> None:
    assert isinstance(
        build_oms(Settings(environment="development", oms_base_url="")),
        MockOmsAdapter,
    )


def test_test_environment_without_oms_url_uses_mock_AC_26() -> None:
    assert isinstance(build_oms(Settings(environment="test", oms_base_url="")), MockOmsAdapter)


def test_production_with_valid_url_uses_http_AC_26() -> None:
    assert isinstance(
        build_oms(Settings(environment="production", oms_base_url="http://oms.test")),
        HttpOmsAdapter,
    )


def test_create_app_fails_without_production_oms_url_AC_26() -> None:
    with pytest.raises(OmsConfigError, match="OMS_BASE_URL"):
        create_app(Settings(environment="production", oms_base_url=""))


def test_create_app_uses_mock_in_test_environment_AC_26() -> None:
    app = create_app(Settings(environment="test", oms_base_url=""))

    assert isinstance(app.state.oms, MockOmsAdapter)


def test_create_app_uses_http_with_valid_url_AC_26() -> None:
    app = create_app(Settings(environment="test", oms_base_url="http://oms.test"))

    assert isinstance(app.state.oms, HttpOmsAdapter)


def test_create_app_override_disables_test_login_AC_26() -> None:
    app = create_app(
        Settings(
            environment="production",
            oms_base_url="http://oms.test",
            model_api_key="dummy",
        )
    )
    client = TestClient(app)

    assert client.post("/session", json={"account_id": "zhang-ming"}).status_code == 404
    assert client.get("/accounts").status_code == 404


def test_create_app_override_enables_test_login_AC_26() -> None:
    app = create_app(Settings(environment="test", oms_base_url=""))
    client = TestClient(app)

    assert client.post("/session", json={"account_id": "zhang-ming"}).status_code == 200
