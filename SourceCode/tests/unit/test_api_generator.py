"""Tests for api.routes.generator module.

Design:
    T-UX-07 (DC-UX-07), DC-0094, DC-0095
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

    def test_generate_uses_command_template_fallback(
        self,
        client: TestClient,
        mock_registry: MagicMock,
        tmp_path: Path,
    ) -> None:
        """LLM output with 'command_template'/'id' maps to assembled .j2 body."""
        # Mock that returns LLM-prompt field names (not API field names)
        llm_mock = MagicMock()

        def mock_chat(system_prompt: str, messages: list, **kwargs) -> str:
            return json.dumps(
                {
                    "id": "ogr2ogr_import",
                    "name": "导入 Carto",
                    "description": "使用 ogr2ogr 导入数据到 Carto",
                    "category": "vector",
                    "command_template": "ogr2ogr -f Carto {{ output }} {{ input }}",
                    "params": [
                        {"name": "input", "type": "file_path", "required": True},
                        {"name": "output", "type": "file_path", "required": True},
                    ],
                    "concepts": [],
                    "notes": [],
                }
            )

        llm_mock.chat = mock_chat
        set_llm_client(llm_mock)

        with patch(
            "api.routes.generator._get_templates_dir",
            return_value=tmp_path,
        ):
            request_body = {
                "document_text": "ogr2ogr Carto import tool",
                "config": {"category": "vector"},
            }
            resp = client.post("/api/generator/generate", json=request_body)
            assert resp.status_code == 200
            data = resp.json()
            assert data["template_id"] == "ogr2ogr_import"
            # Body is now assembled full .j2, not raw command_template
            assert "{# @id ogr2ogr_import #}" in data["body"]
            assert "@echo off" in data["body"]
            assert "ogr2ogr -f Carto {{ output }} {{ input }}" in data["body"]
            assert "params" in data

    def test_generate_token_budget_exceeded(
        self,
        client: TestClient,
        mock_llm_client: MagicMock,
        mock_registry: MagicMock,
    ) -> None:
        """Document exceeding token budget returns 413."""
        # Create a document that exceeds 12000 tokens (48000+ chars)
        long_text = "x" * 50000
        request_body = {
            "document_text": long_text,
            "config": {},
        }

        resp = client.post("/api/generator/generate", json=request_body)
        assert resp.status_code == 413
        assert "过长" in resp.json()["detail"] or "tokens" in resp.json()["detail"].lower()


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

    def test_validate_full_j2_template_passes(self, client: TestClient) -> None:
        """Assembled .j2 with Jinja2 filters passes (| is filter, not pipe)."""
        request_body = {
            "body": (
                "{# @id test #}\n"
                "{# @name Test #}\n"
                "@echo off\n"
                "REM Generated by GIS Agent\n"
                "ogr2ogr {{ output | quote }} {{ input | safe_path | quote }}\n"
                "REM Done\n"
            ),
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
        """Save template to data/templates/{category}/ directory (DC-0092)."""
        with patch(
            "api.routes.generator._get_templates_dir",
            return_value=tmp_path,
        ):
            request_body = {
                "template_id": "my_template",
                "body": (
                    "{# @id my_template #}\n"
                    "{# @category vector #}\n"
                    "ogr2ogr -f GeoJSON out.json in.shp"
                ),
                "overwrite": False,
            }

            resp = client.post("/api/generator/save", json=request_body)
            assert resp.status_code == 200
            data = resp.json()
            assert "saved_path" in data
            assert data["category"] == "vector"

            # Verify file was written to category subdirectory
            saved_file = Path(data["saved_path"])
            assert saved_file.exists()
            assert "my_template" in saved_file.read_text()
            assert "vector" in str(saved_file)

    def test_save_template_overwrite_protection(
        self,
        client: TestClient,
        mock_registry: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Saving to existing file without overwrite returns 409."""
        # Templates are now saved to category subdirectories (DC-0092)
        general_dir = tmp_path / "general"
        general_dir.mkdir(parents=True, exist_ok=True)
        existing_file = general_dir / "existing.j2"
        existing_file.write_text("existing content")

        with patch(
            "api.routes.generator._get_templates_dir",
            return_value=tmp_path,
        ):
            request_body = {
                "template_id": "existing",
                "body": "{# @category general #}\nnew content",
                "overwrite": False,
            }

            resp = client.post("/api/generator/save", json=request_body)
            assert resp.status_code == 409


class TestParseDocument:
    """Tests for POST /api/generator/parse-document."""

    def test_parse_html(self, client: TestClient) -> None:
        """HTML document is cleaned: noisy tags removed, content preserved."""
        request_body = {
            "files": [
                {
                    "content": (
                        "<html><body>"
                        "<nav>Menu</nav>"
                        "<script>alert(1)</script>"
                        "<div><p>ogr2ogr converts vector data.</p></div>"
                        "<footer>Copyright</footer>"
                        "</body></html>"
                    ),
                    "file_type": "html",
                }
            ]
        }

        resp = client.post("/api/generator/parse-document", json=request_body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["files"][0]["file_type"] == "html"
        assert "Menu" not in data["document_text"]
        assert "alert" not in data["document_text"]
        assert "Copyright" not in data["document_text"]
        assert "ogr2ogr converts vector data." in data["document_text"]
        assert "estimated_tokens" in data
        assert data["total_raw_chars"] > 0
        assert data["total_cleaned_chars"] > 0

    def test_parse_markdown(self, client: TestClient) -> None:
        """Markdown document is cleaned: frontmatter removed, links plain."""
        request_body = {
            "files": [
                {
                    "content": (
                        "---\n"
                        "title: gdalwarp\n"
                        "---\n"
                        "# gdalwarp\n\n"
                        "See [docs](https://gdal.org) for more.\n"
                    ),
                    "file_type": "markdown",
                }
            ]
        }

        resp = client.post("/api/generator/parse-document", json=request_body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["files"][0]["file_type"] == "markdown"
        assert "title: gdalwarp" not in data["document_text"]
        assert "docs" in data["document_text"]
        assert "gdal.org" not in data["document_text"]
        assert "gdalwarp" in data["document_text"]

    def test_parse_multi_file(self, client: TestClient) -> None:
        """Multiple files are cleaned and merged with separators."""
        request_body = {
            "files": [
                {
                    "content": "<html><body><p>First doc.</p></body></html>",
                    "file_type": "html",
                },
                {
                    "content": "# Second doc\n\nMore info.",
                    "file_type": "markdown",
                },
            ]
        }

        resp = client.post("/api/generator/parse-document", json=request_body)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["files"]) == 2
        assert data["files"][0]["file_type"] == "html"
        assert data["files"][1]["file_type"] == "markdown"
        assert "First doc." in data["document_text"]
        assert "Second doc" in data["document_text"]
        # Files should be separated
        assert "---" in data["document_text"] or "\n" in data["document_text"]
        assert "estimated_tokens" in data

    def test_parse_large_document(self, client: TestClient) -> None:
        """Parse-document no longer enforces token budget (DC-0095 v2).

        Token check is deferred to the generate endpoint.
        """
        long_content = "x" * 9000  # ~2250 tokens
        request_body = {
            "files": [
                {"content": f"<html><body><p>{long_content}</p></body></html>", "file_type": "html"}
            ]
        }

        resp = client.post("/api/generator/parse-document", json=request_body)
        assert resp.status_code == 200
        data = resp.json()
        assert "document_text" in data
        assert "estimated_tokens" in data

    def test_parse_invalid_type(self, client: TestClient) -> None:
        """Unsupported file_type returns 400."""
        request_body = {
            "files": [
                {"content": "hello", "file_type": "pdf"}
            ]
        }

        resp = client.post("/api/generator/parse-document", json=request_body)
        assert resp.status_code == 400
        assert "Unsupported" in resp.json()["detail"]

    def test_parse_empty_files(self, client: TestClient) -> None:
        """Empty files array returns 400."""
        request_body = {"files": []}

        resp = client.post("/api/generator/parse-document", json=request_body)
        assert resp.status_code == 400
