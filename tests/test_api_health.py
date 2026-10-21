"""GET /health — basic liveness, no backends involved."""
from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.app import ApiConfig, create_app


def test_health_ok():
    client = TestClient(create_app(ApiConfig()))
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}
