from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import admin
from app.config import settings


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(admin.router, prefix="/api")
    return TestClient(app)


def test_admin_api_requires_token_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "secret-token")

    response = _client().post("/api/admin/test-telegram")

    assert response.status_code == 401
    assert response.json()["detail"] == "admin token required"


def test_admin_api_accepts_x_admin_token(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "secret-token")

    response = _client().post(
        "/api/admin/test-telegram",
        headers={"X-Admin-Token": "secret-token"},
    )

    assert response.status_code == 200


def test_admin_api_accepts_bearer_token(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "secret-token")

    response = _client().post(
        "/api/admin/test-telegram",
        headers={"Authorization": "Bearer secret-token"},
    )

    assert response.status_code == 200


def test_admin_api_is_disabled_when_token_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "")

    response = _client().post("/api/admin/test-telegram")

    assert response.status_code == 503
    assert response.json()["detail"] == "ADMIN_API_TOKEN is not configured"
