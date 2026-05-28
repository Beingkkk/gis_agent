"""Unit tests for llm.intent module.

Design: F2, P1
"""

import json
from unittest.mock import MagicMock

import pytest

from llm.exceptions import LLMResponseError
from llm.intent import classify_intent
from llm.models import IntentResult, Message, TemplateInfo
from llm.prompts import PromptBuilder


class TestClassifyIntent:
    """Test classify_intent function."""

    @pytest.fixture
    def builder(self) -> PromptBuilder:
        return PromptBuilder()

    @pytest.fixture
    def client(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def templates(self) -> list[TemplateInfo]:
        """Sample template metadata with names and descriptions."""
        return [
            TemplateInfo(
                id="shp2geojson",
                name="Shapefile 转 GeoJSON",
                description="将 Shapefile 格式转换为 GeoJSON",
            ),
            TemplateInfo(
                id="clip_raster",
                name="栅格裁剪",
                description="使用矢量边界裁剪栅格数据",
            ),
            TemplateInfo(
                id="merge_shp",
                name="合并 Shapefile",
                description="将多个 Shapefile 合并为一个",
            ),
        ]

    def test_returns_intent_result(
        self, client: MagicMock, builder: PromptBuilder, templates: list[TemplateInfo]
    ) -> None:
        """F2: Normal classification returns IntentResult."""
        client.chat.return_value = json.dumps(
            {
                "template_id": "shp2geojson",
                "confidence": 0.95,
                "reasoning": "用户要求将 shp 转为 GeoJSON",
            }
        )

        result = classify_intent(
            user_input="把 shp 转成 GeoJSON",
            available_templates=templates,
            history=[],
            client=client,
            builder=builder,
        )

        assert isinstance(result, IntentResult)
        assert result.template_id == "shp2geojson"
        assert result.confidence == 0.95
        assert "shp" in result.reasoning

    def test_invalid_template_id_sets_zero_confidence(
        self, client: MagicMock, builder: PromptBuilder, templates: list[TemplateInfo]
    ) -> None:
        """F2: Invalid template_id returns confidence=0."""
        client.chat.return_value = json.dumps(
            {
                "template_id": "nonexistent_template",
                "confidence": 0.8,
                "reasoning": "some reasoning",
            }
        )

        result = classify_intent(
            user_input="随便说点什么",
            available_templates=templates,
            history=[],
            client=client,
            builder=builder,
        )

        assert result.confidence == 0.0
        assert result.template_id == ""

    def test_prompt_includes_name_and_description(
        self, client: MagicMock, builder: PromptBuilder, templates: list[TemplateInfo]
    ) -> None:
        """F2: Prompt includes template names and descriptions, not just IDs."""
        client.chat.return_value = json.dumps(
            {"template_id": "clip_raster", "confidence": 0.9, "reasoning": "ok"}
        )

        classify_intent(
            user_input="裁剪栅格",
            available_templates=templates,
            history=[],
            client=client,
            builder=builder,
        )

        call_args = client.chat.call_args
        system_prompt = call_args.kwargs["system_prompt"]
        # Name and description should be in the prompt
        assert "Shapefile 转 GeoJSON" in system_prompt
        assert "将 Shapefile 格式转换为 GeoJSON" in system_prompt
        assert "栅格裁剪" in system_prompt
        assert "使用矢量边界裁剪栅格数据" in system_prompt
        # IDs should also be present
        assert "shp2geojson" in system_prompt
        assert "clip_raster" in system_prompt

    def test_uses_low_temperature(
        self, client: MagicMock, builder: PromptBuilder, templates: list[TemplateInfo]
    ) -> None:
        """F2: Intent classification uses temperature=0.1."""
        client.chat.return_value = json.dumps(
            {"template_id": "shp2geojson", "confidence": 0.9, "reasoning": "ok"}
        )

        classify_intent(
            user_input="test",
            available_templates=templates[:1],
            history=[],
            client=client,
            builder=builder,
        )

        call_args = client.chat.call_args
        assert call_args.kwargs["temperature"] == 0.1

    def test_includes_history_in_messages(
        self, client: MagicMock, builder: PromptBuilder, templates: list[TemplateInfo]
    ) -> None:
        """F2: History messages passed to client."""
        client.chat.return_value = json.dumps(
            {"template_id": "shp2geojson", "confidence": 0.9, "reasoning": "ok"}
        )

        history = [
            Message(role="user", content="之前的输入"),
            Message(role="assistant", content="之前的回复"),
        ]

        classify_intent(
            user_input="现在的输入",
            available_templates=templates[:1],
            history=history,
            client=client,
            builder=builder,
        )

        call_args = client.chat.call_args
        messages = call_args.kwargs["messages"]
        assert len(messages) == 3  # 2 history + 1 current

    def test_non_json_response_raises_llm_response_error(
        self, client: MagicMock, builder: PromptBuilder, templates: list[TemplateInfo]
    ) -> None:
        """F2: Non-JSON response raises LLMResponseError."""
        client.chat.return_value = "这不是 JSON"

        with pytest.raises(LLMResponseError):
            classify_intent(
                user_input="test",
                available_templates=templates[:1],
                history=[],
                client=client,
                builder=builder,
            )

    def test_json_missing_fields_raises_llm_response_error(
        self, client: MagicMock, builder: PromptBuilder, templates: list[TemplateInfo]
    ) -> None:
        """F2: JSON missing required fields raises LLMResponseError."""
        client.chat.return_value = json.dumps({"confidence": 0.9})

        with pytest.raises(LLMResponseError):
            classify_intent(
                user_input="test",
                available_templates=templates[:1],
                history=[],
                client=client,
                builder=builder,
            )

    def test_empty_templates_list(
        self, client: MagicMock, builder: PromptBuilder
    ) -> None:
        """F2: Empty templates list returns zero confidence."""
        client.chat.return_value = json.dumps(
            {"template_id": "", "confidence": 0.0, "reasoning": "no matching template"}
        )

        result = classify_intent(
            user_input="test",
            available_templates=[],
            history=[],
            client=client,
            builder=builder,
        )

        assert result.confidence == 0.0
        assert result.template_id == ""

    def test_markdown_json_code_block_stripped(
        self, client: MagicMock, builder: PromptBuilder, templates: list[TemplateInfo]
    ) -> None:
        """F2: Markdown JSON code block is stripped before parsing."""
        client.chat.return_value = (
            '```json\n'
            '{"template_id": "shp2geojson", "confidence": 0.9, "reasoning": "ok"}\n'
            '```'
        )

        result = classify_intent(
            user_input="test",
            available_templates=templates,
            history=[],
            client=client,
            builder=builder,
        )

        assert result.template_id == "shp2geojson"
        assert result.confidence == 0.9
