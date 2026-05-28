"""Tests for core.registry module.

Design: DC-0041
"""

from pathlib import Path

import pytest

from core.models import ParamDef, TemplateDef
from core.registry import TemplateRegistry


@pytest.fixture
def sample_templates() -> list[TemplateDef]:
    """A small set of template definitions for testing."""
    return [
        TemplateDef(
            id="shp2geojson",
            name="Shapefile 转 GeoJSON",
            description="Convert SHP to GeoJSON",
            template_file="vector/shp2geojson.j2",
            params=[
                ParamDef("input", "file_path", True, "Input SHP path"),
                ParamDef("output", "file_path", True, "Output GeoJSON path"),
                ParamDef("t_srs", "crs", False, "Target CRS", default="EPSG:4326"),
            ],
        ),
        TemplateDef(
            id="clip_raster",
            name="栅格裁剪",
            description="Clip raster with vector boundary",
            template_file="raster/clip_raster.j2",
            params=[
                ParamDef("input", "file_path", True, "Input raster path"),
                ParamDef("output", "file_path", True, "Output raster path"),
            ],
        ),
        TemplateDef(
            id="info_query",
            name="数据信息查询",
            description="Query dataset info",
            template_file="general/info_query.j2",
            params=[ParamDef("input", "file_path", True, "Input data path")],
        ),
    ]


@pytest.fixture
def registry(sample_templates: list[TemplateDef], tmp_path: Path) -> TemplateRegistry:
    """A TemplateRegistry backed by a temporary template directory."""
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "vector").mkdir()
    (template_dir / "raster").mkdir()
    (template_dir / "general").mkdir()
    # Create dummy .j2 files so get_template_path can resolve
    (template_dir / "vector" / "shp2geojson.j2").write_text("{# @id shp2geojson #}\n")
    (template_dir / "raster" / "clip_raster.j2").write_text("{# @id clip_raster #}\n")
    (template_dir / "general" / "info_query.j2").write_text("{# @id info_query #}\n")
    return TemplateRegistry(sample_templates, template_dir)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_init_from_list(sample_templates: list[TemplateDef], tmp_path: Path) -> None:
    """TemplateRegistry can be built from a list of TemplateDefs."""
    reg = TemplateRegistry(sample_templates, tmp_path)
    assert len(reg.list_templates()) == 3


def test_empty_registry(tmp_path: Path) -> None:
    """Empty list produces empty registry."""
    reg: TemplateRegistry = TemplateRegistry([], tmp_path)
    assert reg.list_templates() == []
    assert reg.get_available_ids() == []
    assert reg.get_template("anything") is None


# ---------------------------------------------------------------------------
# get_template
# ---------------------------------------------------------------------------


def test_get_template_by_id(registry: TemplateRegistry) -> None:
    """get_template returns the correct TemplateDef by id."""
    result = registry.get_template("shp2geojson")
    assert result is not None
    assert result.id == "shp2geojson"
    assert result.name == "Shapefile 转 GeoJSON"


def test_get_template_not_found(registry: TemplateRegistry) -> None:
    """get_template returns None for unknown id."""
    assert registry.get_template("nonexistent") is None


# ---------------------------------------------------------------------------
# list_templates
# ---------------------------------------------------------------------------


def test_list_templates_sorted(registry: TemplateRegistry) -> None:
    """list_templates returns all templates sorted by id."""
    templates = registry.list_templates()
    ids = [t.id for t in templates]
    assert ids == ["clip_raster", "info_query", "shp2geojson"]


# ---------------------------------------------------------------------------
# get_available_ids
# ---------------------------------------------------------------------------


def test_get_available_ids(registry: TemplateRegistry) -> None:
    """get_available_ids returns all template ids sorted."""
    ids = registry.get_available_ids()
    assert ids == ["clip_raster", "info_query", "shp2geojson"]


# ---------------------------------------------------------------------------
# get_param_schema
# ---------------------------------------------------------------------------


def test_get_param_schema(registry: TemplateRegistry) -> None:
    """get_param_schema returns the parameter definitions for a template."""
    params = registry.get_param_schema("shp2geojson")
    assert len(params) == 3
    names = [p.name for p in params]
    assert "input" in names
    assert "output" in names
    assert "t_srs" in names


def test_get_param_schema_not_found(registry: TemplateRegistry) -> None:
    """get_param_schema returns empty list for unknown template."""
    assert registry.get_param_schema("nonexistent") == []


# ---------------------------------------------------------------------------
# get_template_path
# ---------------------------------------------------------------------------


def test_get_template_path(registry: TemplateRegistry, tmp_path: Path) -> None:
    """get_template_path resolves to absolute path."""
    path = registry.get_template_path("shp2geojson")
    assert path.is_absolute()
    assert path.name == "shp2geojson.j2"
    assert path.exists()


def test_get_template_path_not_found(registry: TemplateRegistry) -> None:
    """get_template_path for unknown id raises KeyError."""
    with pytest.raises(KeyError):
        registry.get_template_path("nonexistent")
