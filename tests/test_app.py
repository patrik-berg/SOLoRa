"""Tests for the local HTTP service scaffold."""

from fastapi.testclient import TestClient

from solora.app import create_app


def test_health_reports_ready_service() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"service": "solora", "status": "ok"}
