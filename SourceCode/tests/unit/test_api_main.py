"""Tests for api.main module.

Design:
    T-UX-01 (DC-UX-01)
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.main import create_app


class TestCreateApp:
    """Tests for create_app() factory function."""

    def test_app_instance_created(self) -> None:
        app = create_app()
        assert app is not None
        assert isinstance(app, FastAPI)

    def test_app_title(self) -> None:
        app = create_app()
        assert app.title == "GIS Agent API"

    def test_cors_middleware_configured(self) -> None:
        app = create_app()
        client = TestClient(app)
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers
        assert (
            response.headers["access-control-allow-origin"] == "http://localhost:5173"
        )

    def test_cors_allows_credentials(self) -> None:
        app = create_app()
        client = TestClient(app)
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "access-control-allow-credentials" in response.headers

    def test_health_check(self) -> None:
        client = TestClient(create_app())
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_404_unknown_route(self) -> None:
        client = TestClient(create_app())
        response = client.get("/unknown-route")
        assert response.status_code == 404

    def test_templates_route_registered(self) -> None:
        """Templates route is registered (T-UX-03)."""
        from unittest.mock import MagicMock

        from api.dependencies import set_registry

        registry = MagicMock()
        registry.list_templates.return_value = []
        set_registry(registry)

        client = TestClient(create_app())
        response = client.get("/api/templates")
        assert response.status_code == 200
