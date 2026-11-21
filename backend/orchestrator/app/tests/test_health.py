from fastapi.testclient import TestClient

from app.core.config import settings


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["env"] == settings.app_env
    assert body["version"] == "0.1.0"
