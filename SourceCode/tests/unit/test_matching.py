"""Tests for core.matching module.

Design: DC-0094
"""

import pytest

from core.matching import find_matching_templates, score_template_match
from core.models import ParamDef, TemplateDef


@pytest.fixture
def sample_templates() -> list[TemplateDef]:
    return [
        TemplateDef(
            id="shp2geojson",
            name="Shapefile 转 GeoJSON",
            description="Convert SHP to GeoJSON",
            template_file="vector/shp2geojson.j2",
            keywords=["shp", "shapefile", "geojson"],
            concepts=[("Shapefile", "ESRI 开发的矢量数据格式")],
            notes=["输出路径自动加时间戳"],
        ),
        TemplateDef(
            id="clip_raster",
            name="栅格裁剪",
            description="Clip raster",
            template_file="raster/clip_raster.j2",
            keywords=["clip", "裁剪", "tif"],
        ),
    ]


# ---------------------------------------------------------------------------
# score_template_match
# ---------------------------------------------------------------------------


def test_score_keyword_match(sample_templates: list[TemplateDef]) -> None:
    """Keyword match gives highest score."""
    t = sample_templates[0]
    assert score_template_match(t, "shp转geojson") > 0
    assert score_template_match(t, "shp") >= 3


def test_score_concept_match(sample_templates: list[TemplateDef]) -> None:
    """Concept match gives medium score."""
    t = sample_templates[0]
    assert score_template_match(t, "Shapefile是什么") >= 2


def test_score_no_match(sample_templates: list[TemplateDef]) -> None:
    """Irrelevant input scores 0."""
    t = sample_templates[0]
    assert score_template_match(t, "天气预报") == 0


def test_keyword_beats_concept(sample_templates: list[TemplateDef]) -> None:
    """Keyword match (weight 3) scores higher than concept (weight 2)."""
    shp = sample_templates[0]
    raster = sample_templates[1]
    # shp has keyword "shp" (+3) and concept "Shapefile" (+2)
    # raster has no match for "shp"
    shp_score = score_template_match(shp, "shp")
    raster_score = score_template_match(raster, "shp")
    assert shp_score > raster_score


# ---------------------------------------------------------------------------
# find_matching_templates
# ---------------------------------------------------------------------------


def test_find_matching_templates_top_n(
    sample_templates: list[TemplateDef],
) -> None:
    """Returns up to top_n results."""
    results = find_matching_templates(sample_templates, "shp", top_n=1)
    assert len(results) == 1
    assert results[0].id == "shp2geojson"


def test_find_matching_templates_sorted(
    sample_templates: list[TemplateDef],
) -> None:
    """Results are sorted by score descending."""
    # "shapefile" matches shp2geojson (keyword + concept), "clip" matches clip_raster (keyword)
    results = find_matching_templates(sample_templates, "shapefile clip", top_n=2)
    assert len(results) == 2
    # shp2geojson scores higher (keyword "shapefile" = +3, concept "Shapefile" = +2)
    # clip_raster scores lower (keyword "clip" = +3)
    assert results[0].id == "shp2geojson"
    assert results[1].id == "clip_raster"


def test_find_matching_templates_empty(
    sample_templates: list[TemplateDef],
) -> None:
    """No match returns empty list."""
    results = find_matching_templates(sample_templates, "天气预报")
    assert results == []
