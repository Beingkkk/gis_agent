"""Tests for generate.reviewer module.

Design: plan-j2-generate T-GEN-04
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

import pytest

from generate.models import ParamDef, TemplateDefinition
from generate.reviewer import (
    LLMTemplateReviewer,
    _strip_markdown_json,
)


PASS_RESPONSE = '{"passed": true, "issues": [], "suggested_fix": null}'
FAIL_RESPONSE = '{"passed": false, "issues": [{"item": 5, "severity": "error", "message": "t_srs should be crs"}], "suggested_fix": null}'
WARN_RESPONSE = '{"passed": true, "issues": [{"item": 3, "severity": "warning", "message": "missing quote filter"}], "suggested_fix": null}'


class TestStripMarkdownJson:
    def test_plain(self) -> None:
        assert _strip_markdown_json('{"a": 1}') == '{"a": 1}'

    def test_markdown_block(self) -> None:
        assert _strip_markdown_json('```\n{"a": 1}\n```') == '{"a": 1}'


class TestLLMTemplateReviewer:
    """LLMTemplateReviewer tests."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def reviewer(self, mock_client: MagicMock) -> LLMTemplateReviewer:
        return LLMTemplateReviewer(mock_client)

    @pytest.fixture
    def valid_template(self) -> TemplateDefinition:
        return TemplateDefinition(
            id="test_tool",
            name="测试工具",
            description="测试",
            category="vector",
            command_template="echo {{ msg | quote }}",
            params=[ParamDef("msg", "string", True, "消息")],
            concepts=[],
            notes=[],
            common_errors=[],
            seealso=[],
        )

    def test_review_pass(
        self,
        reviewer: LLMTemplateReviewer,
        mock_client: MagicMock,
        valid_template: TemplateDefinition,
    ) -> None:
        mock_client.chat.return_value = PASS_RESPONSE

        result = reviewer.review(valid_template)

        assert result.passed is True
        assert len(result.issues) == 0

    def test_review_fail(
        self,
        reviewer: LLMTemplateReviewer,
        mock_client: MagicMock,
        valid_template: TemplateDefinition,
    ) -> None:
        mock_client.chat.return_value = FAIL_RESPONSE

        result = reviewer.review(valid_template)

        assert result.passed is False
        assert len(result.issues) == 1
        assert result.issues[0].severity == "error"

    def test_review_strict_warning(
        self,
        reviewer: LLMTemplateReviewer,
        mock_client: MagicMock,
        valid_template: TemplateDefinition,
    ) -> None:
        """In strict mode, warnings should also cause failure."""
        mock_client.chat.return_value = WARN_RESPONSE

        result = reviewer.review(valid_template, strict=True)

        assert result.passed is False
        assert len(result.issues) == 1
        assert result.issues[0].severity == "warning"

    def test_review_lenient_warning(
        self,
        reviewer: LLMTemplateReviewer,
        mock_client: MagicMock,
        valid_template: TemplateDefinition,
    ) -> None:
        """In non-strict mode, warnings alone should pass."""
        mock_client.chat.return_value = WARN_RESPONSE

        result = reviewer.review(valid_template, strict=False)

        assert result.passed is True
        assert len(result.issues) == 1

    def test_review_llm_failure(
        self,
        reviewer: LLMTemplateReviewer,
        mock_client: MagicMock,
        valid_template: TemplateDefinition,
    ) -> None:
        mock_client.chat.side_effect = RuntimeError("API down")

        result = reviewer.review(valid_template)

        assert result.passed is False
        assert len(result.issues) == 1
        assert "API down" in result.issues[0].message

    def test_review_parse_failure(
        self,
        reviewer: LLMTemplateReviewer,
        mock_client: MagicMock,
        valid_template: TemplateDefinition,
    ) -> None:
        mock_client.chat.return_value = "not valid json"

        result = reviewer.review(valid_template)

        assert result.passed is False
        assert "parse failed" in result.issues[0].message.lower()
