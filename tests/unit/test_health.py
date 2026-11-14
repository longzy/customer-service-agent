"""健康检查 smoke 测试：保证 pytest 不会因空集合而误判通过。"""

from fastapi.testclient import TestClient

from services.api.main import create_app


def test_health_returns_ok() -> None:
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
