"""Unit tests for llm.prompts module.

Design: DC-0032, DC-0035, ADR-0001
"""

from llm.prompts import PromptBuilder


class TestPromptBuilderInit:
    """Test PromptBuilder initialization."""

    def test_init(self) -> None:
        """Can initialize PromptBuilder."""
        builder = PromptBuilder()
        assert builder is not None


class TestBuildIntentPrompt:
    """Test build_intent_prompt."""

    def test_contains_intent_constraints(self) -> None:
        """DC-0032, F2: Intent prompt contains template selection rules."""
        builder = PromptBuilder()
        prompt = builder.build_intent_prompt("候选模板: shp2geojson")

        assert "候选模板" in prompt or "template" in prompt.lower()
        assert "JSON" in prompt


class TestBuildTemplateQaPrompt:
    """Test build_template_qa_prompt."""

    def test_contains_template_context(self) -> None:
        """DC-0035, P4: Template knowledge context included for Q&A scene."""
        tpl_ctx = "shp2geojson（Shapefile 转 GeoJSON）"
        builder = PromptBuilder()
        prompt = builder.build_template_qa_prompt(tpl_ctx)

        assert "shp2geojson" in prompt
        assert "GeoJSON" in prompt
        assert "模板问答" in prompt


class TestBuildGisExpertPrompt:
    """Test build_gis_expert_prompt."""

    def test_contains_gis_expert_role(self) -> None:
        """DC-0035: GIS expert prompt contains expert role definition."""
        builder = PromptBuilder()
        prompt = builder.build_gis_expert_prompt()

        assert "GIS" in prompt
        assert "专家" in prompt


class TestBuildParamPrompt:
    """Test build_param_prompt."""

    def test_contains_param_constraints(self) -> None:
        """DC-0035, F3: Param prompt contains extraction rules."""
        task_ctx = "当前模板: shp2geojson"
        builder = PromptBuilder()
        prompt = builder.build_param_prompt(task_ctx)

        assert "参数提取" in prompt
        assert "shp2geojson" in prompt


class TestBuildDiagnosisPrompt:
    """Test build_diagnosis_prompt."""

    def test_contains_diagnosis_role(self) -> None:
        """DC-0036, F10: Diagnosis prompt contains expert role."""
        task_ctx = "returncode: 1, stderr: error"
        builder = PromptBuilder()
        prompt = builder.build_diagnosis_prompt(task_ctx)

        assert "诊断" in prompt
        assert "error" in prompt
