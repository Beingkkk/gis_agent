"""Tests for api.routes.templates module.

Design:
    T-UX-03 (DC-UX-02)
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.dependencies import _reset_dependencies, set_registry
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
    """Mock TemplateRegistry with multiple templates."""
    registry = MagicMock()

    shp2geojson = TemplateDef(
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
        concepts=[
            ("GeoJSON", "一种基于JSON的地理数据交换格式"),
            ("Shapefile", "ESRI开发的矢量数据格式"),
        ],
        notes=["输出路径自动加时间戳防覆盖", "确保ogr2ogr可用"],
        seealso=["vector/merge_shp"],
        common_errors=[
            ("Failed to open source file", "检查输入文件路径是否正确"),
        ],
    )

    raster_convert = TemplateDef(
        id="gdal_raster_convert",
        name="栅格格式转换",
        description="将栅格数据从一种格式转换为另一种格式",
        template_file="raster/gdal_raster_convert.j2",
        params=[
            ParamDef(
                name="input",
                type="file_path",
                required=True,
                description="输入栅格文件路径",
            ),
            ParamDef(
                name="output",
                type="file_path",
                required=True,
                description="输出栅格文件路径",
            ),
        ],
    )

    registry.list_templates.return_value = [raster_convert, shp2geojson]
    registry.get_template.side_effect = lambda tid: {
        "shp2geojson": shp2geojson,
        "gdal_raster_convert": raster_convert,
    }.get(tid)

    return registry


class TestListTemplates:
    """Tests for GET /api/templates."""

    def test_list_templates(self, client: TestClient, mock_registry: MagicMock) -> None:
        set_registry(mock_registry)
        resp = client.get("/api/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        # Sorted by id
        assert data[0]["id"] == "gdal_raster_convert"
        assert data[1]["id"] == "shp2geojson"

    def test_list_templates_fields(
        self, client: TestClient, mock_registry: MagicMock
    ) -> None:
        set_registry(mock_registry)
        resp = client.get("/api/templates")
        data = resp.json()
        shp = data[1]
        assert shp["id"] == "shp2geojson"
        assert shp["name"] == "SHP转GeoJSON"
        assert shp["description"] == "将Shapefile转换为GeoJSON格式"
        assert shp["category"] == "vector"
        assert shp["tool_source"] == "GDAL"
        assert shp["tags"] == []

    def test_list_templates_empty(self, client: TestClient) -> None:
        empty_registry = MagicMock()
        empty_registry.list_templates.return_value = []
        set_registry(empty_registry)

        resp = client.get("/api/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert data == []

    def test_list_templates_category_inference(
        self, client: TestClient, mock_registry: MagicMock
    ) -> None:
        set_registry(mock_registry)
        resp = client.get("/api/templates")
        data = resp.json()
        assert data[0]["category"] == "raster"
        assert data[1]["category"] == "vector"


class TestGetTemplateDetail:
    """Tests for GET /api/templates/{template_id}."""

    def test_get_template_detail(
        self, client: TestClient, mock_registry: MagicMock
    ) -> None:
        set_registry(mock_registry)
        resp = client.get("/api/templates/shp2geojson")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "shp2geojson"
        assert data["name"] == "SHP转GeoJSON"

    def test_template_detail_param_defs(
        self, client: TestClient, mock_registry: MagicMock
    ) -> None:
        set_registry(mock_registry)
        resp = client.get("/api/templates/shp2geojson")
        data = resp.json()
        params = data["params"]
        assert len(params) == 3

        input_param = params[0]
        assert input_param["name"] == "input"
        assert input_param["type"] == "file_path"
        assert input_param["required"] is True
        assert input_param["description"] == "输入SHP文件路径"
        assert "default" not in input_param or input_param.get("default") is None

        t_srs = params[2]
        assert t_srs["name"] == "t_srs"
        assert t_srs["required"] is False
        assert t_srs["default"] == "EPSG:4326"

    def test_template_detail_concepts(
        self, client: TestClient, mock_registry: MagicMock
    ) -> None:
        set_registry(mock_registry)
        resp = client.get("/api/templates/shp2geojson")
        data = resp.json()
        concepts = data["concepts"]
        assert len(concepts) == 2
        assert concepts[0]["term"] == "GeoJSON"
        assert concepts[0]["explanation"] == "一种基于JSON的地理数据交换格式"

    def test_template_detail_notes(
        self, client: TestClient, mock_registry: MagicMock
    ) -> None:
        set_registry(mock_registry)
        resp = client.get("/api/templates/shp2geojson")
        data = resp.json()
        assert data["notes"] == ["输出路径自动加时间戳防覆盖", "确保ogr2ogr可用"]

    def test_template_detail_common_errors(
        self, client: TestClient, mock_registry: MagicMock
    ) -> None:
        set_registry(mock_registry)
        resp = client.get("/api/templates/shp2geojson")
        data = resp.json()
        errors = data["common_errors"]
        assert len(errors) == 1
        assert errors[0]["error_text"] == "Failed to open source file"
        assert errors[0]["fix"] == "检查输入文件路径是否正确"

    def test_template_detail_seealso(
        self, client: TestClient, mock_registry: MagicMock
    ) -> None:
        set_registry(mock_registry)
        resp = client.get("/api/templates/shp2geojson")
        data = resp.json()
        assert data["seealso"] == ["vector/merge_shp"]

    def test_get_template_not_found(
        self, client: TestClient, mock_registry: MagicMock
    ) -> None:
        set_registry(mock_registry)
        resp = client.get("/api/templates/nonexistent")
        assert resp.status_code == 404

    def test_get_template_general_category(self, client: TestClient) -> None:
        """Template in general/ directory gets category='general'."""
        registry = MagicMock()
        registry.get_template.return_value = TemplateDef(
            id="gdal_info",
            name="GDAL信息查询",
            description="查询栅格或矢量数据的基本信息",
            template_file="general/gdal_info.j2",
            params=[],
        )
        set_registry(registry)

        resp = client.get("/api/templates/gdal_info")
        data = resp.json()
        assert data["category"] == "general"
