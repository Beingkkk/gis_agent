"""Unit tests for keyword extraction.

Design: plan-qa-optimization v1.0.0
"""

from unittest.mock import MagicMock

import pytest

from llm.keywords import extract_keywords
from llm.models import Message


class TestExtractKeywords:
    """LLM-based keyword extraction for multi-query retrieval."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        """Mock LLMClient."""
        return MagicMock()

    @pytest.fixture
    def mock_builder(self) -> MagicMock:
        """Mock PromptBuilder."""
        builder = MagicMock()
        builder.build_system_prompt.return_value = "test system prompt"
        return builder

    def test_extracts_keywords_from_json_array(
        self, mock_client: MagicMock, mock_builder: MagicMock
    ) -> None:
        """LLM returns JSON array → parsed into keyword list."""
        mock_client.chat.return_value = '["GeoJSON format", "GDAL driver", "ogr2ogr"]'

        result = extract_keywords(
            user_input="GeoJSON 是什么",
            history=[],
            client=mock_client,
            builder=mock_builder,
        )

        assert result == ["GeoJSON format", "GDAL driver", "ogr2ogr"]

    def test_fallback_on_invalid_json(
        self, mock_client: MagicMock, mock_builder: MagicMock
    ) -> None:
        """LLM returns non-JSON → fallback to original input."""
        mock_client.chat.return_value = "GeoJSON, GDAL, driver"

        result = extract_keywords(
            user_input="GeoJSON 是什么",
            history=[],
            client=mock_client,
            builder=mock_builder,
        )

        assert result == ["GeoJSON 是什么"]

    def test_fallback_on_empty_list(
        self, mock_client: MagicMock, mock_builder: MagicMock
    ) -> None:
        """LLM returns empty JSON array → fallback to original input."""
        mock_client.chat.return_value = "[]"

        result = extract_keywords(
            user_input="GeoJSON 是什么",
            history=[],
            client=mock_client,
            builder=mock_builder,
        )

        assert result == ["GeoJSON 是什么"]

    def test_deduplicates_and_filters_empty(
        self, mock_client: MagicMock, mock_builder: MagicMock
    ) -> None:
        """Duplicate keywords and empty strings are filtered."""
        mock_client.chat.return_value = '["a", "b", "a", "", "b", "c"]'

        result = extract_keywords(
            user_input="test",
            history=[],
            client=mock_client,
            builder=mock_builder,
        )

        assert result == ["a", "b", "c"]

    def test_passes_system_prompt_with_keyword_instruction(
        self, mock_client: MagicMock, mock_builder: MagicMock
    ) -> None:
        """System prompt should mention keyword extraction."""
        mock_client.chat.return_value = '["k1"]'

        extract_keywords(
            user_input="test",
            history=[],
            client=mock_client,
            builder=mock_builder,
        )

        call_kwargs = mock_client.chat.call_args.kwargs
        system_prompt = call_kwargs["system_prompt"]
        assert "关键词" in system_prompt
        assert "JSON" in system_prompt

    def test_passes_user_input_as_current_input(
        self, mock_client: MagicMock, mock_builder: MagicMock
    ) -> None:
        """User input is passed as current_input to LLM chat."""
        mock_client.chat.return_value = '["k1"]'

        extract_keywords(
            user_input="GeoJSON 是什么",
            history=[],
            client=mock_client,
            builder=mock_builder,
        )

        call_kwargs = mock_client.chat.call_args.kwargs
        assert call_kwargs["current_input"] == "GeoJSON 是什么"

    def test_includes_history_in_messages(
        self, mock_client: MagicMock, mock_builder: MagicMock
    ) -> None:
        """History messages are included in the LLM call."""
        mock_client.chat.return_value = '["k1"]'
        history = [Message(role="user", content="prev")]

        extract_keywords(
            user_input="test",
            history=history,
            client=mock_client,
            builder=mock_builder,
        )

        call_kwargs = mock_client.chat.call_args.kwargs
        messages = call_kwargs["messages"]
        assert len(messages) == 1
        assert messages[0].role == "user"
        assert messages[0].content == "prev"

    def test_limits_to_max_keywords(
        self, mock_client: MagicMock, mock_builder: MagicMock
    ) -> None:
        """More than 5 keywords are truncated to first 5."""
        mock_client.chat.return_value = '["a", "b", "c", "d", "e", "f", "g"]'

        result = extract_keywords(
            user_input="test",
            history=[],
            client=mock_client,
            builder=mock_builder,
        )

        assert len(result) == 5
        assert result == ["a", "b", "c", "d", "e"]

    def test_strips_whitespace_from_keywords(
        self, mock_client: MagicMock, mock_builder: MagicMock
    ) -> None:
        """Keywords with surrounding whitespace are stripped."""
        mock_client.chat.return_value = '["  a  ", "  b"]'

        result = extract_keywords(
            user_input="test",
            history=[],
            client=mock_client,
            builder=mock_builder,
        )

        assert result == ["a", "b"]
