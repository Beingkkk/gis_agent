"""Tests for generate.models module.

Design: plan-j2-generate T-GEN-01, DC-0082
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

import pytest

from generate.models import ExtractedDoc, ParamDef, TemplateDefinition


class TestParamDef:
    """ParamDef dataclass tests."""

    def test_valid_param(self) -> None:
        p = ParamDef(
            name="input",
            type="file_path",
            required=True,
            description="输入文件路径",
        )
        assert p.name == "input"
        assert p.type == "file_path"
        assert p.required is True
        assert p.default is None

    def test_valid_optional_with_default(self) -> None:
        p = ParamDef(
            name="format",
            type="string",
            required=False,
            description="输出格式",
            default="GeoJSON",
        )
        assert p.default == "GeoJSON"

    def test_invalid_type(self) -> None:
        with pytest.raises(ValueError, match="Invalid param type"):
            ParamDef(
                name="input",
                type="invalid_type",
                required=True,
                description="输入文件路径",
            )


class TestTemplateDefinition:
    """TemplateDefinition validation tests."""

    @pytest.fixture
    def valid_params(self) -> list[ParamDef]:
        return [
            ParamDef("input", "file_path", True, "输入文件路径"),
            ParamDef("output", "file_path", True, "输出文件路径"),
            ParamDef("t_srs", "crs", False, "目标坐标系", default="EPSG:4326"),
        ]

    def test_valid_template(self, valid_params: list[ParamDef]) -> None:
        t = TemplateDefinition(
            id="shp2geojson",
            name="Shapefile转GeoJSON",
            description="将Shapefile转换为GeoJSON格式",
            category="vector",
            command_template='ogr2ogr -f "GeoJSON" {{ output | quote }} {{ input | quote }}',
            params=valid_params,
            concepts=["GeoJSON是基于JSON的地理数据格式"],
            notes=["输出路径自动加时间戳"],
            common_errors=[{"error_text": "Unable to open", "explanation": "路径错误"}],
            seealso=[],
        )
        assert t.id == "shp2geojson"

    def test_invalid_id_format(self, valid_params: list[ParamDef]) -> None:
        with pytest.raises(ValueError, match="Invalid id format"):
            TemplateDefinition(
                id="SHP2GeoJSON",
                name="无效ID",
                description="测试",
                category="vector",
                command_template="cmd",
                params=valid_params,
                concepts=[],
                notes=[],
                common_errors=[],
                seealso=[],
            )

    def test_invalid_category(self, valid_params: list[ParamDef]) -> None:
        with pytest.raises(ValueError, match="Invalid category"):
            TemplateDefinition(
                id="test",
                name="测试",
                description="测试",
                category="invalid",
                command_template="cmd",
                params=valid_params,
                concepts=[],
                notes=[],
                common_errors=[],
                seealso=[],
            )

    def test_required_param_with_default(self, valid_params: list[ParamDef]) -> None:
        bad_params = [
            ParamDef("input", "file_path", True, "输入", default="default.shp"),
        ]
        with pytest.raises(ValueError, match="Required param.*cannot have default"):
            TemplateDefinition(
                id="test",
                name="测试",
                description="测试",
                category="vector",
                command_template="cmd",
                params=bad_params,
                concepts=[],
                notes=[],
                common_errors=[],
                seealso=[],
            )

    def test_undeclared_var_in_template(self) -> None:
        params = [ParamDef("input", "file_path", True, "输入")]
        with pytest.raises(ValueError, match="undeclared"):
            TemplateDefinition(
                id="test",
                name="测试",
                description="测试",
                category="vector",
                command_template="cmd {{ output | quote }}",
                params=params,
                concepts=[],
                notes=[],
                common_errors=[],
                seealso=[],
            )

    def test_optional_flag_in_template(self) -> None:
        """Optional flags with {% if %} should not trigger undeclared error."""
        params = [
            ParamDef("input", "file_path", True, "输入"),
            ParamDef("output", "file_path", True, "输出"),
            ParamDef("append", "boolean", False, "追加模式"),
        ]
        t = TemplateDefinition(
            id="test",
            name="测试",
            description="测试",
            category="vector",
            command_template="cmd{% if append %} -append{% endif %} {{ output | quote }} {{ input | quote }}",
            params=params,
            concepts=[],
            notes=[],
            common_errors=[],
            seealso=[],
        )
        assert t.id == "test"


class TestExtractedDoc:
    """ExtractedDoc tests."""

    def test_creation(self) -> None:
        doc = ExtractedDoc(
            title="ogr2ogr",
            synopsis="Usage: ogr2ogr [options] dst src",
            description="Converts simple features data between file formats.",
            options=[{"name": "-f", "description": "Output format"}],
        )
        assert doc.title == "ogr2ogr"
        assert len(doc.options) == 1
