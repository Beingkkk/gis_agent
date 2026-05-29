"""Tests for api.routes.session module.

Design:
    T-UX-02 (DC-UX-02, DC-UX-03)
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.dependencies import (
    _reset_dependencies,
    set_registry,
    set_template_engine,
    set_validator,
)
from api.main import create_app
from core.models import ParamDef, TemplateDef
from templates.engine import RenderedScript


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
    """Mock TemplateRegistry with a shp2geojson template."""
    registry = MagicMock()
    template = TemplateDef(
        id="shp2geojson",
        name="SHP转GeoJSON",
        description="将Shapefile转换为GeoJSON格式",
        template_file="vector/shp2geojson.j2",
        params=[
            ParamDef(
                name="input",
                type="file_path",
                required=True,
                description="输入SHP文件路径",
            ),
            ParamDef(
                name="output",
                type="file_path",
                required=True,
                description="输出GeoJSON文件路径",
            ),
            ParamDef(
                name="t_srs",
                type="crs",
                required=False,
                description="目标坐标系",
                default="EPSG:4326",
            ),
        ],
    )
    registry.list_templates.return_value = [template]
    registry.get_template.return_value = template
    return registry


@pytest.fixture
def mock_validator() -> MagicMock:
    """Mock ParamValidator that validates all params."""
    validator = MagicMock()
    validator.validate_all.return_value = (
        {"input": "test.shp", "output": "test.json", "t_srs": "EPSG:4326"},
        [],
    )
    return validator


@pytest.fixture
def mock_engine() -> MagicMock:
    """Mock TemplateEngine that returns a fixed script."""
    engine = MagicMock()
    engine.render.return_value = RenderedScript(
        content='ogr2ogr -f "GeoJSON" test.json test.shp',
        command_lines=['ogr2ogr -f "GeoJSON" test.json test.shp'],
        platform=MagicMock(),
        output_path="shp2geojson.bat",
    )
    return engine


class TestCreateSession:
    """Tests for POST /api/session."""

    def test_create_session(self, client: TestClient) -> None:
        response = client.post("/api/session")
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["state"] == "IDLE"
        assert data["task_context"]["template_id"] is None

    def test_create_session_with_workspace(self, client: TestClient) -> None:
        # workspace parameter is accepted but does not affect response yet
        response = client.post("/api/session?workspace=/data/gis")
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data


class TestProcessIntent:
    """Tests for POST /api/session/{id}/intent."""

    def test_process_intent_match(
        self,
        client: TestClient,
        mock_registry: MagicMock,
    ) -> None:
        set_registry(mock_registry)
        # Create session
        resp = client.post("/api/session")
        session_id = resp.json()["session_id"]

        # Process intent with matching keywords
        resp = client.post(
            f"/api/session/{session_id}/intent",
            json={"input": "shp转geojson"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "PARAM_COLLECT"
        assert data["task_context"]["template_id"] == "shp2geojson"

    def test_process_intent_no_match(
        self,
        client: TestClient,
        mock_registry: MagicMock,
    ) -> None:
        set_registry(mock_registry)
        resp = client.post("/api/session")
        session_id = resp.json()["session_id"]

        resp = client.post(
            f"/api/session/{session_id}/intent",
            json={"input": "something completely unrelated"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "INTENT_CONFIRM"
        assert data["task_context"]["candidates"] is not None

    def test_process_intent_session_not_found(self, client: TestClient) -> None:
        resp = client.post(
            "/api/session/nonexistent-id/intent",
            json={"input": "shp转geojson"},
        )
        assert resp.status_code == 404


class TestLockTemplate:
    """Tests for POST /api/session/{id}/lock."""

    def test_lock_template(
        self,
        client: TestClient,
        mock_registry: MagicMock,
    ) -> None:
        set_registry(mock_registry)
        resp = client.post("/api/session")
        session_id = resp.json()["session_id"]

        resp = client.post(
            f"/api/session/{session_id}/lock",
            json={"template_id": "shp2geojson"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "PARAM_COLLECT"
        assert data["task_context"]["template_id"] == "shp2geojson"

    def test_lock_template_invalid_id(
        self,
        client: TestClient,
        mock_registry: MagicMock,
    ) -> None:
        set_registry(mock_registry)
        mock_registry.get_template.return_value = None
        resp = client.post("/api/session")
        session_id = resp.json()["session_id"]

        resp = client.post(
            f"/api/session/{session_id}/lock",
            json={"template_id": "nonexistent"},
        )
        assert resp.status_code == 400


class TestSubmitParams:
    """Tests for POST /api/session/{id}/params."""

    def test_submit_params_complete(
        self,
        client: TestClient,
        mock_registry: MagicMock,
        mock_validator: MagicMock,
        mock_engine: MagicMock,
    ) -> None:
        set_registry(mock_registry)
        set_validator(mock_validator)
        set_template_engine(mock_engine)

        resp = client.post("/api/session")
        session_id = resp.json()["session_id"]
        # Lock template first
        client.post(
            f"/api/session/{session_id}/lock",
            json={"template_id": "shp2geojson"},
        )

        resp = client.post(
            f"/api/session/{session_id}/params",
            json={"params": {"input": "test.shp", "output": "test.json"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "SCRIPT_PREVIEW"
        assert data["script_preview"] is not None

    def test_submit_params_incomplete(
        self,
        client: TestClient,
        mock_registry: MagicMock,
    ) -> None:
        set_registry(mock_registry)
        # Validator returns missing params
        validator = MagicMock()
        validator.validate_all.return_value = ({}, ["Missing required: input"])
        set_validator(validator)

        resp = client.post("/api/session")
        session_id = resp.json()["session_id"]
        client.post(
            f"/api/session/{session_id}/lock",
            json={"template_id": "shp2geojson"},
        )

        resp = client.post(
            f"/api/session/{session_id}/params",
            json={"params": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "PARAM_COLLECT"
        assert "input" in data["task_context"]["missing_params"]

    def test_submit_params_validation_error(
        self,
        client: TestClient,
        mock_registry: MagicMock,
    ) -> None:
        set_registry(mock_registry)
        validator = MagicMock()
        validator.validate_all.return_value = (
            {},
            ["Parameter 'input' contains illegal characters"],
        )
        set_validator(validator)

        resp = client.post("/api/session")
        session_id = resp.json()["session_id"]
        client.post(
            f"/api/session/{session_id}/lock",
            json={"template_id": "shp2geojson"},
        )

        resp = client.post(
            f"/api/session/{session_id}/params",
            json={"params": {"input": "test;rm -rf /", "output": "test.json"}},
        )
        assert resp.status_code == 400


class TestExecuteScript:
    """Tests for POST /api/session/{id}/execute."""

    def test_execute_script_triggers(self, client: TestClient) -> None:
        resp = client.post("/api/session")
        session_id = resp.json()["session_id"]

        resp = client.post(f"/api/session/{session_id}/execute")
        assert resp.status_code == 202
        data = resp.json()
        assert "execution_id" in data

    def test_execute_dry_run(self, client: TestClient) -> None:
        resp = client.post("/api/session")
        session_id = resp.json()["session_id"]

        resp = client.post(f"/api/session/{session_id}/execute?dry_run=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("dry_run") is True


class TestClearSession:
    """Tests for POST /api/session/{id}/clear."""

    def test_clear_session(self, client: TestClient) -> None:
        resp = client.post("/api/session")
        session_id = resp.json()["session_id"]

        resp = client.post(f"/api/session/{session_id}/clear")
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "IDLE"
        assert data["task_context"]["template_id"] is None
