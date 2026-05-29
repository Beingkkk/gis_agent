"""Tests for generate.generator module.

Design: plan-j2-generate T-GEN-03
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

import pytest

from generate.generator import LLMTemplateGenerator, _strip_markdown_json
from generate.models import ExtractedDoc


VALID_JSON_RESPONSE = """{
  "id": "test_tool",
  "name": "测试工具",
  "description": "一个测试工具",
  "category": "vector",
  "command_template": "echo {{ msg | quote }}",
  "params": [
    {"name": "msg", "type": "string", "required": true, "description": "消息"}
  ],
  "concepts": ["测试概念"],
  "notes": ["测试说明"],
  "common_errors": [{"error_text": "Error", "explanation": "错误"}],
  "seealso": []
}"""


class TestStripMarkdownJson:
    """_strip_markdown_json helper tests."""

    def test_plain_json(self) -> None:
        assert _strip_markdown_json('{"a": 1}') == '{"a": 1}'

    def test_with_markdown_block(self) -> None:
        assert _strip_markdown_json('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_with_generic_block(self) -> None:
        assert _strip_markdown_json('```\n{"a": 1}\n```') == '{"a": 1}'


class TestLLMTemplateGenerator:
    """LLMTemplateGenerator tests."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def generator(self, mock_client: MagicMock) -> LLMTemplateGenerator:
        return LLMTemplateGenerator(mock_client)

    @pytest.fixture
    def sample_doc(self) -> ExtractedDoc:
        return ExtractedDoc(
            title="test_tool",
            synopsis="Usage: test_tool [options]",
            description="A test tool.",
        )

    def test_generate_success(
        self,
        generator: LLMTemplateGenerator,
        mock_client: MagicMock,
        sample_doc: ExtractedDoc,
    ) -> None:
        mock_client.chat.return_value = VALID_JSON_RESPONSE

        result, error = generator.generate(sample_doc)

        assert error == ""
        assert result is not None
        assert result.id == "test_tool"
        assert result.name == "测试工具"
        assert len(result.params) == 1
        assert result.params[0].name == "msg"
        assert result.params[0].type == "string"

    def test_generate_llm_failure(
        self,
        generator: LLMTemplateGenerator,
        mock_client: MagicMock,
        sample_doc: ExtractedDoc,
    ) -> None:
        mock_client.chat.side_effect = RuntimeError("API error")

        result, error = generator.generate(sample_doc)

        assert result is None
        assert "LLM call failed" in error

    def test_generate_invalid_json(
        self,
        generator: LLMTemplateGenerator,
        mock_client: MagicMock,
        sample_doc: ExtractedDoc,
    ) -> None:
        mock_client.chat.return_value = "not json at all"

        result, error = generator.generate(sample_doc)

        assert result is None
        assert "JSON parse failed" in error

    def test_generate_validation_failure(
        self,
        generator: LLMTemplateGenerator,
        mock_client: MagicMock,
        sample_doc: ExtractedDoc,
    ) -> None:
        # Missing required field 'category'
        bad_json = '{"id": "test", "name": "Test", "description": "d", "command_template": "cmd", "params": []}'
        mock_client.chat.return_value = bad_json

        result, error = generator.generate(sample_doc)

        assert result is None
        assert "validation" in error.lower() or "missing" in error.lower()

    def test_generate_markdown_json(
        self,
        generator: LLMTemplateGenerator,
        mock_client: MagicMock,
        sample_doc: ExtractedDoc,
    ) -> None:
        mock_client.chat.return_value = "```json\n" + VALID_JSON_RESPONSE + "\n```"

        result, error = generator.generate(sample_doc)

        assert error == ""
        assert result is not None
        assert result.id == "test_tool"
