"""Tests for generate.renderer module.

Design: plan-j2-generate T-GEN-05
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

import pytest

from generate.models import ParamDef, TemplateDefinition
from generate.renderer import render_j2
from templates.scanner import scan_templates


class TestRenderJ2:
    """render_j2 tests."""

    @pytest.fixture
    def minimal_template(self) -> TemplateDefinition:
        return TemplateDefinition(
            id="test_template",
            name="测试模板",
            description="这是一个测试模板",
            category="vector",
            command_template="echo {{ msg | quote }}",
            params=[
                ParamDef("msg", "string", True, "消息内容"),
            ],
            concepts=["测试概念"],
            notes=["测试说明"],
            common_errors=[{"error_text": "Error", "explanation": "错误原因"}],
            seealso=["other_template"],
        )

    def test_contains_id(self, minimal_template: TemplateDefinition) -> None:
        result = render_j2(minimal_template)
        assert "{# @id test_template #}" in result

    def test_contains_name(self, minimal_template: TemplateDefinition) -> None:
        result = render_j2(minimal_template)
        assert "{# @name 测试模板 #}" in result

    def test_contains_param(self, minimal_template: TemplateDefinition) -> None:
        result = render_j2(minimal_template)
        assert "{# @param msg string required 消息内容 #}" in result

    def test_contains_command(self, minimal_template: TemplateDefinition) -> None:
        result = render_j2(minimal_template)
        assert "echo {{ msg | quote }}" in result

    def test_contains_concept(self, minimal_template: TemplateDefinition) -> None:
        result = render_j2(minimal_template)
        assert '{# @concept "测试概念" #}' in result

    def test_contains_common_error(self, minimal_template: TemplateDefinition) -> None:
        result = render_j2(minimal_template)
        assert '{# @common_error "Error" — 错误原因 #}' in result

    def test_scanable(
        self, minimal_template: TemplateDefinition, tmp_path: Path
    ) -> None:
        """Generated content must be parseable by scan_templates()."""
        j2_content = render_j2(minimal_template)
        j2_path = tmp_path / "test_template.j2"
        j2_path.write_text(j2_content, encoding="utf-8")

        scanned = scan_templates(tmp_path)
        assert len(scanned) == 1
        assert scanned[0].id == "test_template"
        assert scanned[0].name == "测试模板"
        assert len(scanned[0].params) == 1
        assert scanned[0].params[0].name == "msg"

    def test_optional_param_with_default(self, tmp_path: Path) -> None:
        template = TemplateDefinition(
            id="default_test",
            name="默认值测试",
            description="测试默认参数",
            category="vector",
            command_template="echo {{ fmt | quote }}",
            params=[
                ParamDef("fmt", "string", False, "格式", default="GeoJSON"),
            ],
            concepts=[],
            notes=[],
            common_errors=[],
            seealso=[],
        )
        result = render_j2(template)
        assert "default=GeoJSON" in result
