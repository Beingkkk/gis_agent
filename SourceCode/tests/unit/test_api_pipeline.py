"""Tests for api.routes.pipeline module.

Design:
    T-UX-06 (DC-UX-06)
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.dependencies import (
    _reset_dependencies,
    set_registry,
    set_template_engine,
)
from api.main import create_app
from core.models import ParamDef, TemplateDef


@pytest.fixture(autouse=True)
def reset_deps() -> None:
    """Reset global dependencies before each test."""
    _reset_dependencies()


@pytest.fixture
def client() -> TestClient:
    """TestClient with basic app."""
    return TestClient(create_app())


@pytest.fixture
def mock_registry() -> MagicMock:
    """Mock TemplateRegistry with test templates."""
    registry = MagicMock()

    template1 = TemplateDef(
        id="shp2geojson",
        name="SHP to GeoJSON",
        description="Convert SHP to GeoJSON",
        template_file="vector/shp2geojson.j2",
        params=[
            ParamDef(
                name="input", type="file_path", required=True, description="Input SHP"
            ),
            ParamDef(
                name="output",
                type="file_path",
                required=True,
                description="Output GeoJSON",
            ),
        ],
    )

    template2 = TemplateDef(
        id="reproject",
        name="Reproject",
        description="Reproject vector data",
        template_file="vector/reproject.j2",
        params=[
            ParamDef(
                name="input", type="file_path", required=True, description="Input file"
            ),
            ParamDef(
                name="output",
                type="file_path",
                required=True,
                description="Output file",
            ),
            ParamDef(name="t_srs", type="crs", required=True, description="Target CRS"),
        ],
    )

    def get_template(tid: str) -> TemplateDef | None:
        if tid == "shp2geojson":
            return template1
        if tid == "reproject":
            return template2
        return None

    registry.get_template = get_template
    set_registry(registry)
    return registry


@pytest.fixture
def mock_template_engine() -> MagicMock:
    """Mock TemplateEngine that returns predictable rendered scripts."""
    engine = MagicMock()

    def mock_render(template_def: TemplateDef, params: dict[str, str]) -> MagicMock:
        rendered = MagicMock()
        rendered.content = (
            f"ogr2ogr -f GeoJSON"
            f" {params.get('output', 'out')}"
            f" {params.get('input', 'in')}"
        )
        rendered.platform.name = "WINDOWS"
        return rendered

    def mock_validate(
        template_def: TemplateDef, params: dict[str, str]
    ) -> tuple[bool, str | None]:
        for param in template_def.params:
            if param.required and param.name not in params:
                return (False, f"Missing required parameter: {param.name}")
        return (True, None)

    engine.render = mock_render
    engine.validate_params_for_template = mock_validate
    set_template_engine(engine)
    return engine


class TestPipelinePreview:
    """Tests for POST /api/pipeline (script preview)."""

    def test_preview_pipeline_single_step(
        self,
        client: TestClient,
        mock_registry: MagicMock,
        mock_template_engine: MagicMock,
    ) -> None:
        """Single step Pipeline returns rendered script."""
        request_body = {
            "steps": [
                {
                    "order": 0,
                    "template_id": "shp2geojson",
                    "params": {"input": "roads.shp", "output": "roads.json"},
                }
            ],
            "autoLinks": [],
        }

        resp = client.post("/api/pipeline", json=request_body)
        assert resp.status_code == 200
        data = resp.json()
        assert "script" in data
        assert "roads.shp" in data["script"]
        assert "roads.json" in data["script"]

    def test_preview_pipeline_two_steps(
        self,
        client: TestClient,
        mock_registry: MagicMock,
        mock_template_engine: MagicMock,
    ) -> None:
        """Two-step Pipeline returns merged script with both commands."""
        request_body = {
            "steps": [
                {
                    "order": 0,
                    "template_id": "shp2geojson",
                    "params": {"input": "roads.shp", "output": "roads.json"},
                },
                {
                    "order": 1,
                    "template_id": "reproject",
                    "params": {
                        "input": "roads.json",
                        "output": "roads_4326.json",
                        "t_srs": "EPSG:4326",
                    },
                },
            ],
            "autoLinks": [],
        }

        resp = client.post("/api/pipeline", json=request_body)
        assert resp.status_code == 200
        data = resp.json()
        assert "script" in data
        script = data["script"]
        assert "roads.shp" in script
        assert "roads_4326.json" in script

    def test_preview_pipeline_auto_link(
        self,
        client: TestClient,
        mock_registry: MagicMock,
        mock_template_engine: MagicMock,
    ) -> None:
        """AutoLinks pass output from step 1 to input of step 2."""
        request_body = {
            "steps": [
                {
                    "order": 0,
                    "template_id": "shp2geojson",
                    "params": {"input": "roads.shp", "output": "roads.json"},
                },
                {
                    "order": 1,
                    "template_id": "reproject",
                    "params": {
                        "input": "PLACEHOLDER",
                        "output": "roads_4326.json",
                        "t_srs": "EPSG:4326",
                    },
                },
            ],
            "autoLinks": [
                {
                    "fromStep": 0,
                    "fromParam": "output",
                    "toStep": 1,
                    "toParam": "input",
                }
            ],
        }

        resp = client.post("/api/pipeline", json=request_body)
        assert resp.status_code == 200
        data = resp.json()
        assert "script" in data

    def test_preview_pipeline_invalid_template(
        self,
        client: TestClient,
        mock_registry: MagicMock,
        mock_template_engine: MagicMock,
    ) -> None:
        """Invalid template_id returns 400."""
        request_body = {
            "steps": [
                {
                    "order": 0,
                    "template_id": "nonexistent",
                    "params": {"input": "test.shp"},
                }
            ],
            "autoLinks": [],
        }

        resp = client.post("/api/pipeline", json=request_body)
        assert resp.status_code == 400
        assert "nonexistent" in resp.json()["detail"]

    def test_preview_pipeline_missing_param(
        self,
        client: TestClient,
        mock_registry: MagicMock,
        mock_template_engine: MagicMock,
    ) -> None:
        """Missing required parameter returns 400."""
        request_body = {
            "steps": [
                {
                    "order": 0,
                    "template_id": "shp2geojson",
                    "params": {"input": "roads.shp"},  # missing "output"
                }
            ],
            "autoLinks": [],
        }

        resp = client.post("/api/pipeline", json=request_body)
        assert resp.status_code == 400
        assert "output" in resp.json()["detail"]


class TestPipelineExecute:
    """Tests for POST /api/pipeline/execute."""

    def test_execute_pipeline(
        self,
        client: TestClient,
        mock_registry: MagicMock,
        mock_template_engine: MagicMock,
    ) -> None:
        """Execute endpoint returns execution_id with 202 status."""
        request_body = {
            "steps": [
                {
                    "order": 0,
                    "template_id": "shp2geojson",
                    "params": {"input": "roads.shp", "output": "roads.json"},
                }
            ],
            "autoLinks": [],
        }

        resp = client.post("/api/pipeline/execute", json=request_body)
        assert resp.status_code == 202
        data = resp.json()
        assert "execution_id" in data
