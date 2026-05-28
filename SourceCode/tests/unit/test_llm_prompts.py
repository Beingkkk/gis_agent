"""Unit tests for llm.prompts module.

Design: DC-0032, DC-0035
"""

from llm.prompts import PromptBuilder


class TestPromptBuilderInit:
    """Test PromptBuilder initialization."""

    def test_init_without_agents_md(self) -> None:
        """Can initialize without Agents.md."""
        builder = PromptBuilder(agents_md=None)
        assert builder is not None

    def test_init_with_agents_md(self) -> None:
        """Can initialize with Agents.md content."""
        builder = PromptBuilder(agents_md="# Project config\n- default_crs: 4326")
        assert builder is not None


class TestBuildSystemPrompt:
    """Test PromptBuilder.build_system_prompt()."""

    def test_contains_fixed_safety_constraints(self) -> None:
        """DC-0032, P1: System prompt contains safety constraints."""
        builder = PromptBuilder()
        prompt = builder.build_system_prompt()

        assert "模板" in prompt or "template" in prompt.lower()
        assert "命令" in prompt or "command" in prompt.lower()

    def test_contains_agents_md_when_provided(self) -> None:
        """DC-0035, F11: Agents.md content injected into system prompt."""
        agents_md = "# 城市道路项目\n- 默认坐标系: EPSG:4326"
        builder = PromptBuilder(agents_md=agents_md)
        prompt = builder.build_system_prompt()

        assert "城市道路项目" in prompt
        assert "EPSG:4326" in prompt

    def test_omits_agents_md_when_none(self) -> None:
        """DC-0035: No Agents.md section when none provided."""
        builder = PromptBuilder(agents_md=None)
        prompt = builder.build_system_prompt()

        # Should not contain placeholder for missing agents_md
        assert "Agents.md" not in prompt

    def test_contains_rag_context_when_provided(self) -> None:
        """DC-0035, P4: RAG context included for Q&A scene."""
        rag_ctx = "[1] ogr2ogr supports GeoJSON output..."
        builder = PromptBuilder()
        prompt = builder.build_system_prompt(rag_context=rag_ctx)

        assert "GeoJSON" in prompt
        assert "ogr2ogr" in prompt

    def test_omits_rag_context_when_none(self) -> None:
        """DC-0035: No RAG section when no context."""
        builder = PromptBuilder()
        prompt = builder.build_system_prompt()

        # RAG-specific markers should not appear
        assert "文档片段" not in prompt

    def test_contains_task_context_when_provided(self) -> None:
        """DC-0035: Task context included for param extraction."""
        task_ctx = "当前模板: shp2geojson, 已收集: {input: 'roads.shp'}"
        builder = PromptBuilder()
        prompt = builder.build_system_prompt(task_context=task_ctx)

        assert "shp2geojson" in prompt

    def test_prompt_order_fixed_constraints_first(self) -> None:
        """DC-0035: Fixed constraints come first in prompt."""
        agents_md = "Project config"
        rag_ctx = "Document context"
        builder = PromptBuilder(agents_md=agents_md)
        prompt = builder.build_system_prompt(rag_context=rag_ctx)

        # Safety constraints should appear before dynamic content
        safety_idx = prompt.find("模板")
        agents_idx = prompt.find("Project config")

        if safety_idx != -1 and agents_idx != -1:
            assert safety_idx < agents_idx


class TestPromptBuilderForIntent:
    """Test prompts for intent classification scenario."""

    def test_build_intent_prompt_structure(self) -> None:
        """F2: Intent classification prompt contains template constraint."""
        builder = PromptBuilder()
        prompt = builder.build_system_prompt()

        # Should reference template selection
        assert "模板" in prompt or "template" in prompt.lower()
