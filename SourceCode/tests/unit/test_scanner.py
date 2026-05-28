"""Tests for templates.scanner module.

Design: DC-0050, DC-0041
"""

from pathlib import Path

import pytest

from templates.scanner import parse_j2_header, scan_templates

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def template_dir(tmp_path: Path) -> Path:
    """Create a temporary templates directory with subdirs."""
    for sub in ("vector", "raster", "general"):
        (tmp_path / sub).mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# parse_j2_header
# ---------------------------------------------------------------------------


def _write_j2(path: Path, content: str) -> None:
    """Helper: write .j2 with explicit UTF-8 encoding."""
    path.write_text(content, encoding="utf-8")


def test_parse_header_minimal(template_dir: Path) -> None:
    """Minimal valid header with only id."""
    j2 = template_dir / "test.j2"
    _write_j2(
        j2,
        "{# @id foo #}\n"
        "{# @name Foo Name #}\n"
        "{# @description Foo desc #}\n"
        "echo hello\n",
    )
    result = parse_j2_header(j2)
    assert result.id == "foo"
    assert result.name == "Foo Name"
    assert result.description == "Foo desc"
    assert result.params == []


def test_parse_header_with_params(template_dir: Path) -> None:
    """Header with required and optional params including default."""
    j2 = template_dir / "test.j2"
    _write_j2(
        j2,
        "{# @id shp2geojson #}\n"
        "{# @name Shapefile 转 GeoJSON #}\n"
        "{# @description 转换 #}\n"
        "{# @param input file_path required 输入路径 #}\n"
        "{# @param t_srs crs optional 目标坐标系 default=EPSG:4326 #}\n"
        "ogr2ogr ...\n",
    )
    result = parse_j2_header(j2)
    assert result.id == "shp2geojson"
    assert len(result.params) == 2

    p1 = result.params[0]
    assert p1.name == "input"
    assert p1.type == "file_path"
    assert p1.required is True
    assert p1.description == "输入路径"
    assert p1.default is None

    p2 = result.params[1]
    assert p2.name == "t_srs"
    assert p2.type == "crs"
    assert p2.required is False
    assert p2.description == "目标坐标系"
    assert p2.default == "EPSG:4326"


def test_parse_header_missing_id(template_dir: Path) -> None:
    """Missing @id raises ValueError."""
    j2 = template_dir / "bad.j2"
    _write_j2(j2, "{# @name No ID #}\n")
    with pytest.raises(ValueError, match="Missing @id"):
        parse_j2_header(j2)


def test_parse_header_name_fallback(template_dir: Path) -> None:
    """Missing @name uses @id as fallback."""
    j2 = template_dir / "test.j2"
    _write_j2(j2, "{# @id fallback_id #}\n")
    result = parse_j2_header(j2)
    assert result.name == "fallback_id"


def test_parse_header_only_non_param_keys(template_dir: Path) -> None:
    """Non-@param keys are stored in data dict."""
    j2 = template_dir / "test.j2"
    _write_j2(
        j2,
        "{# @id x #}\n{# @custom_key custom value #}\necho\n",
    )
    result = parse_j2_header(j2)
    assert result.id == "x"


def test_parse_param_invalid_line(template_dir: Path) -> None:
    """Invalid @param line (too few tokens) raises ValueError."""
    j2 = template_dir / "test.j2"
    _write_j2(
        j2,
        "{# @id x #}\n{# @param only_one_token #}\necho\n",
    )
    with pytest.raises(ValueError, match="Invalid @param"):
        parse_j2_header(j2)


# ---------------------------------------------------------------------------
# scan_templates
# ---------------------------------------------------------------------------


def test_scan_empty_dir(tmp_path: Path) -> None:
    """Empty directory returns empty list."""
    assert scan_templates(tmp_path) == []


def test_scan_multiple_files(template_dir: Path) -> None:
    """Scan discovers all .j2 files and returns sorted TemplateDefs."""
    _write_j2(
        template_dir / "a.j2",
        "{# @id alpha #}\n{# @name Alpha #}\n{# @description A #}\n",
    )
    _write_j2(
        template_dir / "b.j2",
        "{# @id beta #}\n{# @name Beta #}\n{# @description B #}\n",
    )
    _write_j2(
        template_dir / "vector" / "c.j2",
        "{# @id charlie #}\n{# @name Charlie #}\n{# @description C #}\n",
    )

    results = scan_templates(template_dir)
    ids = [t.id for t in results]
    assert ids == ["alpha", "beta", "charlie"]

    # Sub-directory templates store relative path
    charlie = next(t for t in results if t.id == "charlie")
    assert charlie.template_file == "vector/c.j2"


def test_scan_skips_bad_files(template_dir: Path, caplog) -> None:
    """Files without @id are skipped with a warning."""
    _write_j2(
        template_dir / "good.j2",
        "{# @id good #}\n{# @name Good #}\n{# @description G #}\n",
    )
    _write_j2(template_dir / "bad.j2", "{# @name Bad #}\n")

    import logging

    with caplog.at_level(logging.WARNING):
        results = scan_templates(template_dir)

    assert len(results) == 1
    assert results[0].id == "good"
    assert "bad.j2" in caplog.text


def test_scan_ignores_non_j2(template_dir: Path) -> None:
    """Non-.j2 files are ignored."""
    _write_j2(
        template_dir / "a.j2",
        "{# @id a #}\n{# @name A #}\n{# @description A #}\n",
    )
    _write_j2(template_dir / "readme.txt", "not a template\n")

    results = scan_templates(template_dir)
    assert len(results) == 1
    assert results[0].id == "a"


# ---------------------------------------------------------------------------
# Integration: scan real templates directory
# ---------------------------------------------------------------------------


def test_scan_real_templates() -> None:
    """Scan the actual data/templates/ directory bundled with the project."""
    data_dir = Path(__file__).resolve().parents[2] / "data" / "templates"
    if not data_dir.exists():
        pytest.skip("data/templates/ not found")

    results = scan_templates(data_dir)
    ids = [t.id for t in results]
    assert "shp2geojson" in ids
    assert "clip_raster" in ids
    assert "info_query" in ids

    # Verify params are parsed correctly for shp2geojson
    shp = next(t for t in results if t.id == "shp2geojson")
    assert shp.name == "Shapefile 转 GeoJSON"
    param_names = [p.name for p in shp.params]
    assert "input" in param_names
    assert "output" in param_names
    assert "t_srs" in param_names

    t_srs = next(p for p in shp.params if p.name == "t_srs")
    assert t_srs.required is False
    assert t_srs.default == "EPSG:4326"
