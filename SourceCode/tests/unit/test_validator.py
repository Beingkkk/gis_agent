"""Tests for core.validator module.

Design: DC-0042
"""

from pathlib import Path

import pytest

from core.models import ParamDef, TemplateDef
from core.validator import ParamValidator
from core.workspace import Workspace


@pytest.fixture
def validator(tmp_path: Path) -> ParamValidator:
    """A ParamValidator backed by a temporary workspace."""
    workspace = Workspace(tmp_path)
    return ParamValidator(workspace)


@pytest.fixture
def sample_template() -> TemplateDef:
    """A template with various parameter types."""
    return TemplateDef(
        id="test",
        name="Test",
        description="Test template",
        template_file="test.j2",
        params=[
            ParamDef("input", "file_path", True, "Input file path"),
            ParamDef("output", "file_path", True, "Output file path"),
            ParamDef("s_srs", "crs", False, "Source CRS", default="EPSG:4326"),
            ParamDef("format", "string", False, "Output format"),
            ParamDef("verbose", "boolean", False, "Verbose mode"),
            ParamDef("threads", "integer", False, "Number of threads"),
        ],
    )


# ---------------------------------------------------------------------------
# file_path type
# ---------------------------------------------------------------------------


def test_file_path_ok(validator: ParamValidator) -> None:
    """Valid relative file path passes."""
    param = ParamDef("input", "file_path", True, "Input path")
    ok, error = validator.validate(param, "data/roads.shp")
    assert ok is True
    assert error is None


def test_file_path_empty(validator: ParamValidator) -> None:
    """Empty file path fails."""
    param = ParamDef("input", "file_path", True, "Input path")
    ok, error = validator.validate(param, "")
    assert ok is False
    assert error is not None
    assert "input" in error


def test_file_path_must_exist_missing(
    validator: ParamValidator, tmp_path: Path
) -> None:
    """must_exist=True with missing file fails."""
    param = ParamDef("input", "file_path", True, "Input path", must_exist=True)
    ok, error = validator.validate(param, "nonexistent.shp")
    assert ok is False
    assert "not exist" in error.lower() or "不存在" in error


def test_file_path_must_exist_present(
    validator: ParamValidator, tmp_path: Path
) -> None:
    """must_exist=True with existing file passes."""
    existing = tmp_path / "exists.shp"
    existing.write_text("dummy")
    param = ParamDef("input", "file_path", True, "Input path", must_exist=True)
    ok, error = validator.validate(param, "exists.shp")
    assert ok is True
    assert error is None


# ---------------------------------------------------------------------------
# crs type
# ---------------------------------------------------------------------------


def test_crs_epsg_ok(validator: ParamValidator) -> None:
    """Valid EPSG code passes."""
    param = ParamDef("srs", "crs", True, "CRS")
    ok, error = validator.validate(param, "EPSG:4326")
    assert ok is True
    assert error is None


def test_crs_invalid(validator: ParamValidator) -> None:
    """Invalid CRS format fails."""
    param = ParamDef("srs", "crs", True, "CRS")
    ok, error = validator.validate(param, "INVALID")
    assert ok is False
    assert error is not None


def test_crs_empty(validator: ParamValidator) -> None:
    """Empty CRS fails when required."""
    param = ParamDef("srs", "crs", True, "CRS")
    ok, error = validator.validate(param, "")
    assert ok is False


# ---------------------------------------------------------------------------
# string type
# ---------------------------------------------------------------------------


def test_string_ok(validator: ParamValidator) -> None:
    """Non-empty string passes."""
    param = ParamDef("name", "string", True, "Name")
    ok, error = validator.validate(param, "GeoJSON")
    assert ok is True
    assert error is None


def test_string_empty(validator: ParamValidator) -> None:
    """Empty string fails."""
    param = ParamDef("name", "string", True, "Name")
    ok, error = validator.validate(param, "")
    assert ok is False
    assert error is not None


# ---------------------------------------------------------------------------
# boolean type
# ---------------------------------------------------------------------------


def test_boolean_true_values(validator: ParamValidator) -> None:
    """Various true representations pass and convert."""
    param = ParamDef("flag", "boolean", False, "Flag")
    for value in ("yes", "true", "1", "YES", "True"):
        ok, error = validator.validate(param, value)
        assert ok is True, f"{value!r} should be valid"
        assert error is None


def test_boolean_false_values(validator: ParamValidator) -> None:
    """Various false representations pass and convert."""
    param = ParamDef("flag", "boolean", False, "Flag")
    for value in ("no", "false", "0", "NO", "False"):
        ok, error = validator.validate(param, value)
        assert ok is True, f"{value!r} should be valid"
        assert error is None


def test_boolean_invalid(validator: ParamValidator) -> None:
    """Non-boolean string fails."""
    param = ParamDef("flag", "boolean", False, "Flag")
    ok, error = validator.validate(param, "maybe")
    assert ok is False
    assert error is not None


# ---------------------------------------------------------------------------
# integer type
# ---------------------------------------------------------------------------


def test_integer_ok(validator: ParamValidator) -> None:
    """Valid integer string passes."""
    param = ParamDef("count", "integer", False, "Count")
    ok, error = validator.validate(param, "4")
    assert ok is True
    assert error is None


def test_integer_invalid(validator: ParamValidator) -> None:
    """Non-integer string fails."""
    param = ParamDef("count", "integer", False, "Count")
    ok, error = validator.validate(param, "abc")
    assert ok is False
    assert error is not None


def test_integer_negative(validator: ParamValidator) -> None:
    """Negative integer passes."""
    param = ParamDef("count", "integer", False, "Count")
    ok, error = validator.validate(param, "-1")
    assert ok is True
    assert error is None


# ---------------------------------------------------------------------------
# validate_all
# ---------------------------------------------------------------------------


def test_validate_all_required_missing(validator: ParamValidator) -> None:
    """Missing required param produces error."""
    template = TemplateDef(
        id="t",
        name="T",
        description="D",
        template_file="t.j2",
        params=[
            ParamDef("input", "file_path", True, "Input"),
            ParamDef("output", "file_path", True, "Output"),
        ],
    )
    valid_params, errors = validator.validate_all(template, {"input": "a.shp"})
    assert len(errors) == 1
    assert "output" in errors[0]
    assert "input" in valid_params  # provided param still returned


def test_validate_all_optional_with_default(validator: ParamValidator) -> None:
    """Optional param without value gets default filled in."""
    template = TemplateDef(
        id="t",
        name="T",
        description="D",
        template_file="t.j2",
        params=[
            ParamDef("input", "file_path", True, "Input"),
            ParamDef("s_srs", "crs", False, "CRS", default="EPSG:4326"),
        ],
    )
    valid_params, errors = validator.validate_all(template, {"input": "a.shp"})
    assert len(errors) == 0
    assert valid_params["s_srs"] == "EPSG:4326"


def test_validate_all_returns_converted_values(
    validator: ParamValidator,
) -> None:
    """Boolean values are converted to string 'true'/'false'."""
    template = TemplateDef(
        id="t",
        name="T",
        description="D",
        template_file="t.j2",
        params=[
            ParamDef("input", "file_path", True, "Input"),
            ParamDef("verbose", "boolean", False, "Verbose"),
        ],
    )
    valid_params, errors = validator.validate_all(
        template, {"input": "a.shp", "verbose": "yes"}
    )
    assert len(errors) == 0
    # Boolean is normalized to lowercase string for template rendering
    assert valid_params["verbose"] == "true"


def test_validate_all_complete(validator: ParamValidator) -> None:
    """All required params present and valid -> no errors."""
    template = TemplateDef(
        id="t",
        name="T",
        description="D",
        template_file="t.j2",
        params=[
            ParamDef("input", "file_path", True, "Input"),
            ParamDef("output", "file_path", True, "Output"),
        ],
    )
    valid_params, errors = validator.validate_all(
        template, {"input": "a.shp", "output": "b.geojson"}
    )
    assert len(errors) == 0
    assert valid_params == {"input": "a.shp", "output": "b.geojson"}


def test_crs_raw_digits_normalized(validator: ParamValidator) -> None:
    """Raw EPSG digits are auto-prefixed with 'EPSG:'."""
    template = TemplateDef(
        id="t",
        name="T",
        description="D",
        template_file="t.j2",
        params=[ParamDef("srs", "crs", True, "CRS")],
    )
    valid_params, errors = validator.validate_all(template, {"srs": "4326"})
    assert len(errors) == 0
    assert valid_params["srs"] == "EPSG:4326"


def test_crs_full_format_preserved(validator: ParamValidator) -> None:
    """Full EPSG:xxxx format is preserved unchanged."""
    template = TemplateDef(
        id="t",
        name="T",
        description="D",
        template_file="t.j2",
        params=[ParamDef("srs", "crs", True, "CRS")],
    )
    valid_params, errors = validator.validate_all(template, {"srs": "EPSG:3857"})
    assert len(errors) == 0
    assert valid_params["srs"] == "EPSG:3857"
