"""Tests for templates.engine module.

Design: DC-0050, DC-0051, DC-0052, DC-0053, DC-0054
"""

import sys
from pathlib import Path

import pytest

from core.models import ParamDef, TemplateDef
from core.workspace import Workspace
from templates.engine import (
    Platform,
    RenderedScript,
    RenderError,
    ScriptSecurityChecker,
    SecurityCheckError,
    TemplateEngine,
    TemplateError,
    TemplateNotFoundError,
    quote_filter,
    safe_path_filter,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    """Create a Workspace instance using a temporary directory."""
    return Workspace(tmp_path)


@pytest.fixture
def template_dir(tmp_path: Path) -> Path:
    """Create a temporary templates directory with subdirs."""
    for sub in ("vector", "raster", "general"):
        (tmp_path / sub).mkdir()
    return tmp_path


@pytest.fixture
def engine(template_dir: Path, workspace: Workspace) -> TemplateEngine:
    """Create a TemplateEngine instance."""
    return TemplateEngine(template_dir, workspace)


@pytest.fixture
def shp2geojson_def() -> TemplateDef:
    """A sample TemplateDef for shp2geojson."""
    return TemplateDef(
        id="shp2geojson",
        name="Shapefile to GeoJSON",
        description="Convert Shapefile to GeoJSON",
        template_file="vector/shp2geojson.j2",
        params=[
            ParamDef("input", "file_path", True, "Input Shapefile path"),
            ParamDef("output", "file_path", True, "Output GeoJSON path"),
            ParamDef("s_srs", "crs", False, "Source CRS"),
            ParamDef("t_srs", "crs", False, "Target CRS", default="EPSG:4326"),
        ],
    )


# ---------------------------------------------------------------------------
# T-04: Platform + RenderedScript
# ---------------------------------------------------------------------------


def test_platform_enum_values() -> None:
    """Platform Enum has expected values."""
    assert Platform.WINDOWS.value == "windows"
    assert Platform.UNIX.value == "unix"


def test_rendered_script_fields() -> None:
    """RenderedScript dataclass has correct fields."""
    rs = RenderedScript(
        content="echo hello",
        command_lines=["echo hello"],
        platform=Platform.WINDOWS,
        output_path="out.bat",
    )
    assert rs.content == "echo hello"
    assert rs.command_lines == ["echo hello"]
    assert rs.platform == Platform.WINDOWS
    assert rs.output_path == "out.bat"


# ---------------------------------------------------------------------------
# T-06: quote_filter
# ---------------------------------------------------------------------------


def test_quote_filter_simple_string() -> None:
    """Simple string without metacharacters is preserved (or safely wrapped)."""
    result = quote_filter("roads.shp")
    assert "roads.shp" in result
    # shlex.quote behaviour is platform-dependent: POSIX wraps in single
    # quotes; Windows passes through for safe strings.


def test_quote_filter_space_in_filename() -> None:
    """Filename with spaces gets quoted."""
    result = quote_filter("my file.shp")
    assert result.startswith("'")
    assert result.endswith("'")
    assert "my file.shp" in result


def test_quote_filter_shell_metacharacter() -> None:
    """Shell metacharacters get escaped."""
    result = quote_filter("file; rm -rf /")
    assert ";" not in result or result.startswith("'")
    assert result != "file; rm -rf /"


# ---------------------------------------------------------------------------
# T-07: safe_path_filter
# ---------------------------------------------------------------------------


def test_safe_path_filter_relative(workspace: Workspace) -> None:
    """Relative path resolves against workspace root."""
    result = safe_path_filter("data/roads.shp", workspace)
    expected = str(workspace.root / "data" / "roads.shp")
    assert result == expected


def test_safe_path_filter_absolute(workspace: Workspace, tmp_path: Path) -> None:
    """Absolute path is passed through (not restricted to workspace)."""
    abs_path = str(tmp_path / "external" / "data.tif")
    result = safe_path_filter(abs_path, workspace)
    assert result == abs_path


# ---------------------------------------------------------------------------
# T-08: ScriptSecurityChecker
# ---------------------------------------------------------------------------


def test_security_check_normal_command_passes() -> None:
    """Normal GDAL command passes security check."""
    checker = ScriptSecurityChecker()
    ok, reason = checker.check("ogr2ogr -f GeoJSON out.json in.shp")
    assert ok is True
    assert reason is None


def test_security_check_semicolon_blocked() -> None:
    """Command separator ; is blocked."""
    checker = ScriptSecurityChecker()
    ok, reason = checker.check("cmd1; cmd2")
    assert ok is False
    assert reason is not None


def test_security_check_ampersand_blocked() -> None:
    """Command separator & is blocked."""
    checker = ScriptSecurityChecker()
    ok, reason = checker.check("cmd1 && cmd2")
    assert ok is False


def test_security_check_pipe_blocked() -> None:
    """Command pipe | is blocked."""
    checker = ScriptSecurityChecker()
    ok, reason = checker.check("cmd1 | cmd2")
    assert ok is False


def test_security_check_dollar_substitution_blocked() -> None:
    """$(...) command substitution is blocked."""
    checker = ScriptSecurityChecker()
    ok, reason = checker.check("echo $(whoami)")
    assert ok is False


def test_security_check_backtick_blocked() -> None:
    """Backtick command substitution is blocked."""
    checker = ScriptSecurityChecker()
    ok, reason = checker.check("echo `whoami`")
    assert ok is False


def test_security_check_path_traversal_blocked() -> None:
    """Path traversal ../../ is blocked."""
    checker = ScriptSecurityChecker()
    ok, reason = checker.check("cat ../../etc/passwd")
    assert ok is False


# ---------------------------------------------------------------------------
# T-09: TemplateEngine.render
# ---------------------------------------------------------------------------


def test_basic_render_windows(
    engine: TemplateEngine,
    template_dir: Path,
    shp2geojson_def: TemplateDef,
) -> None:
    """Basic render on Windows produces @echo off header."""
    j2 = template_dir / "vector" / "shp2geojson.j2"
    j2.write_text(
        "@echo off\n"
        "REM Generated\n"
        'ogr2ogr -f "GeoJSON" {{ output | quote }} {{ input | quote }}\n'
    )

    result = engine.render(
        shp2geojson_def,
        {"input": "data/roads.shp", "output": "roads_out.geojson"},
        platform=Platform.WINDOWS,
    )
    assert isinstance(result, RenderedScript)
    assert "@echo off" in result.content
    assert result.platform == Platform.WINDOWS


def test_optional_param_omitted(
    engine: TemplateEngine,
    template_dir: Path,
    shp2geojson_def: TemplateDef,
) -> None:
    """Optional param not provided -> conditional block not rendered."""
    j2 = template_dir / "vector" / "shp2geojson.j2"
    j2.write_text(
        'ogr2ogr -f "GeoJSON" {{ output | quote }} {{ input | quote }}'
        "{% if t_srs %} -t_srs {{ t_srs | quote }}{% endif %}\n"
    )

    result = engine.render(
        shp2geojson_def,
        {"input": "data/roads.shp", "output": "roads_out.geojson"},
        platform=Platform.WINDOWS,
    )
    assert "-t_srs" not in result.content


def test_optional_param_included(
    engine: TemplateEngine,
    template_dir: Path,
    shp2geojson_def: TemplateDef,
) -> None:
    """Optional param provided -> conditional block rendered."""
    j2 = template_dir / "vector" / "shp2geojson.j2"
    j2.write_text(
        'ogr2ogr -f "GeoJSON" {{ output | quote }} {{ input | quote }}'
        "{% if t_srs %} -t_srs {{ t_srs | quote }}{% endif %}\n"
    )

    result = engine.render(
        shp2geojson_def,
        {
            "input": "data/roads.shp",
            "output": "roads_out.geojson",
            "t_srs": "EPSG:4326",
        },
        platform=Platform.WINDOWS,
    )
    assert "-t_srs" in result.content
    assert "EPSG:4326" in result.content


def test_shell_escape_in_render(
    engine: TemplateEngine,
    template_dir: Path,
    shp2geojson_def: TemplateDef,
) -> None:
    """Filenames with spaces are properly quoted in rendered output."""
    j2 = template_dir / "vector" / "shp2geojson.j2"
    j2.write_text('ogr2ogr -f "GeoJSON" {{ output | quote }} {{ input | quote }}\n')

    result = engine.render(
        shp2geojson_def,
        {"input": "my roads.shp", "output": "my output.geojson"},
        platform=Platform.WINDOWS,
    )
    # shlex.quote should wrap space-containing strings in single quotes
    assert "'my roads.shp'" in result.content or '"my roads.shp"' in result.content


def test_whitelist_blocks_injection_before_render(
    engine: TemplateEngine,
    template_dir: Path,
) -> None:
    """Whitelist blocks injection before render reaches security check."""
    j2_raw = template_dir / "vector" / "raw.j2"
    j2_raw.write_text("echo {{ value }}\n")
    raw_def = TemplateDef(
        id="raw",
        name="Raw",
        description="Raw",
        template_file="vector/raw.j2",
        params=[ParamDef("value", "string", True, "Value")],
    )

    # The ; character fails whitelist validation → RenderError (before security check)
    with pytest.raises(RenderError):
        engine.render(raw_def, {"value": "hello; rm -rf /"}, platform=Platform.WINDOWS)


def test_template_not_found(
    engine: TemplateEngine, shp2geojson_def: TemplateDef
) -> None:
    """Missing .j2 file raises TemplateNotFoundError."""
    bad_def = TemplateDef(
        id="missing",
        name="Missing",
        description="Missing",
        template_file="vector/does_not_exist.j2",
        params=[],
    )
    with pytest.raises(TemplateNotFoundError):
        engine.render(bad_def, {}, platform=Platform.WINDOWS)


def test_render_unix_platform(
    engine: TemplateEngine,
    template_dir: Path,
    shp2geojson_def: TemplateDef,
) -> None:
    """Unix platform produces shebang header."""
    j2 = template_dir / "vector" / "shp2geojson.j2"
    j2.write_text(
        "#!/bin/bash\n"
        "# Generated\n"
        'ogr2ogr -f "GeoJSON" {{ output | quote }} {{ input | quote }}\n'
    )

    result = engine.render(
        shp2geojson_def,
        {"input": "data/roads.shp", "output": "roads_out.geojson"},
        platform=Platform.UNIX,
    )
    assert "#!/bin/bash" in result.content
    assert result.platform == Platform.UNIX


def test_render_default_platform_is_current(
    engine: TemplateEngine,
    template_dir: Path,
    shp2geojson_def: TemplateDef,
) -> None:
    """No platform arg -> defaults to current platform."""
    j2 = template_dir / "vector" / "shp2geojson.j2"
    j2.write_text("echo hello\n")

    result = engine.render(
        shp2geojson_def,
        {"input": "a.shp", "output": "b.geojson"},
    )
    # On Windows: WINDOWS, else UNIX
    if sys.platform == "win32":
        assert result.platform == Platform.WINDOWS
    else:
        assert result.platform == Platform.UNIX


# ---------------------------------------------------------------------------
# T-09: TemplateEngine.validate_params_for_template
# ---------------------------------------------------------------------------


def test_validate_missing_required_param(
    engine: TemplateEngine, shp2geojson_def: TemplateDef
) -> None:
    """Missing required param returns (False, error_message)."""
    ok, error = engine.validate_params_for_template(
        shp2geojson_def,
        {"output": "out.geojson"},  # missing "input"
    )
    assert ok is False
    assert error is not None
    assert "input" in error


def test_validate_whitelist_blocks_illegal_char(
    engine: TemplateEngine, shp2geojson_def: TemplateDef
) -> None:
    """Param value containing ; is blocked by whitelist."""
    ok, error = engine.validate_params_for_template(
        shp2geojson_def,
        {"input": "file; rm -rf /", "output": "out.geojson"},
    )
    assert ok is False
    assert error is not None


def test_validate_all_params_valid(
    engine: TemplateEngine, shp2geojson_def: TemplateDef
) -> None:
    """All required params present and valid -> (True, None)."""
    ok, error = engine.validate_params_for_template(
        shp2geojson_def,
        {"input": "data/roads.shp", "output": "roads_out.geojson"},
    )
    assert ok is True
    assert error is None


# ---------------------------------------------------------------------------
# T-05: Exception hierarchy
# ---------------------------------------------------------------------------


def test_exception_hierarchy() -> None:
    """All template exceptions inherit from TemplateError."""
    assert issubclass(TemplateNotFoundError, TemplateError)
    assert issubclass(RenderError, TemplateError)
    assert issubclass(SecurityCheckError, TemplateError)


def test_template_not_found_error_message() -> None:
    """TemplateNotFoundError includes template file path."""
    exc = TemplateNotFoundError("vector/missing.j2")
    assert "missing" in str(exc)
