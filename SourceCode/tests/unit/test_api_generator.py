"""Tests for api.routes.generator module.

Design:
    T-UX-07 (DC-UX-07)
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import (
    _reset_dependencies,
    set_llm_client,
    set_registry,
)
from api.main import create_app


@pytest.fixture(autouse=True)
def reset_deps() -> None:
    """Reset global dependencies before each test."""
    _reset_dependencies()


@pytest.fixture
def client() -> TestClient:
    """TestClient with basic app."""
    return TestClient(create_app())


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Mock LLMClient that returns predictable template JSON."""
    client = MagicMock()

    def mock_chat(system_prompt: str, messages: list, **kwargs) -> str:
        return json.dumps(
            {
                "template_id": "test_convert",
                "name": "Test Convert",
                "description": "A test template for conversion",
                "body": (
                    "{# @id test_convert #}\n"
                    "ogr2ogr -f GeoJSON {{ output }} {{ input }}"
                ),
                "params": [
                    {"name": "input", "type": "file_path", "required": True},
                    {"name": "output", "type": "file_path", "required": True},
                ],
                "concepts": [],
                "notes": ["Test note"],
            }
        )

    client.chat = mock_chat
    set_llm_client(client)
    return client


@pytest.fixture
def mock_registry() -> MagicMock:
    """Mock TemplateRegistry."""
    registry = MagicMock()
    registry.list_templates.return_value = []
    set_registry(registry)
    return registry


class TestGenerateTemplate:
    """Tests for POST /api/generator/generate."""

    def test_generate_template(
        self,
        client: TestClient,
        mock_llm_client: MagicMock,
        mock_registry: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Valid document text returns generated template."""
        with patch(
            "api.routes.generator._get_templates_dir",
            return_value=tmp_path,
        ):
            request_body = {
                "document_text": "Convert vector data using ogr2ogr",
                "config": {"category": "vector", "tool_source": "GDAL"},
            }

            resp = client.post("/api/generator/generate", json=request_body)
            assert resp.status_code == 200
            data = resp.json()
            assert data["template_id"] == "test_convert"
            assert "body" in data
            assert "params" in data

    def test_generate_invalid_input(
        self,
        client: TestClient,
        mock_llm_client: MagicMock,
        mock_registry: MagicMock,
    ) -> None:
        """Empty document_text returns 400."""
        request_body = {
            "document_text": "",
            "config": {},
        }

        resp = client.post("/api/generator/generate", json=request_body)
        assert resp.status_code == 400


class TestValidateTemplate:
    """Tests for POST /api/generator/validate."""

    def test_validate_template_safe(self, client: TestClient) -> None:
        """Safe template passes validation."""
        request_body = {
            "body": "ogr2ogr -f GeoJSON {{ output }} {{ input }}",
        }

        resp = client.post("/api/generator/validate", json=request_body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["errors"] == []

    def test_validate_template_unsafe(self, client: TestClient) -> None:
        """Template with dangerous patterns fails validation."""
        request_body = {
            "body": "ogr2ogr -f GeoJSON {{ output }}; rm -rf /",
        }

        resp = client.post("/api/generator/validate", json=request_body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0


class TestSaveTemplate:
    """Tests for POST /api/generator/save."""

    def test_save_template(
        self,
        client: TestClient,
        mock_registry: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Save template to data/templates/ directory."""
        with patch(
            "api.routes.generator._get_templates_dir",
            return_value=tmp_path,
        ):
            request_body = {
                "template_id": "my_template",
                "body": "{# @id my_template #}\nogr2ogr -f GeoJSON out.json in.shp",
                "overwrite": False,
            }

            resp = client.post("/api/generator/save", json=request_body)
            assert resp.status_code == 200
            data = resp.json()
            assert "saved_path" in data

            # Verify file was written
            saved_file = Path(data["saved_path"])
            assert saved_file.exists()
            assert "my_template" in saved_file.read_text()

    def test_save_template_overwrite_protection(
        self,
        client: TestClient,
        mock_registry: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Saving to existing file without overwrite returns 409."""
        existing_file = tmp_path / "existing.j2"
        existing_file.write_text("existing content")

        with patch(
            "api.routes.generator._get_templates_dir",
            return_value=tmp_path,
        ):
            request_body = {
                "template_id": "existing",
                "body": "new content",
                "overwrite": False,
            }

            resp = client.post("/api/generator/save", json=request_body)
            assert resp.status_code == 409
