"""Unit tests for llm.qa module.

Design: F1, P4
"""

from unittest.mock import MagicMock

import pytest

from llm.models import Message
from llm.prompts import PromptBuilder
from llm.qa import answer_question
from rag.retriever import RetrievedDocument


class TestAnswerQuestion:
    """Test answer_question function."""

    @pytest.fixture
    def builder(self) -> PromptBuilder:
        return PromptBuilder()

    @pytest.fixture
    def client(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def retrieved_docs(self) -> list:
        from rag.preprocess import DocumentChunk

        return [
            RetrievedDocument(
                chunk=DocumentChunk(
                    id="ogr2ogr-001",
                    source_file="programs/ogr2ogr.html",
                    title="ogr2ogr",
                    section="Supported formats",
                    content="ogr2ogr supports GeoJSON, Shapefile, KML...",
                    token_estimate=32,
                ),
                distance=0.1,
            ),
            RetrievedDocument(
                chunk=DocumentChunk(
                    id="ogr2ogr-002",
                    source_file="programs/ogr2ogr.html",
                    title="ogr2ogr",
                    section="Options",
                    content="-f format_name: output format",
                    token_estimate=16,
                ),
                distance=0.2,
            ),
        ]

    def test_returns_answer_string(
        self, client: MagicMock, builder: PromptBuilder, retrieved_docs: list
    ) -> None:
        """F1: Returns natural language answer."""
        client.chat.return_value = "ogr2ogr 支持 GeoJSON、Shapefile、KML 等格式。"

        result = answer_question(
            user_input="ogr2ogr 支持哪些格式？",
            retrieved_docs=retrieved_docs,
            history=[],
            client=client,
            builder=builder,
        )

        assert isinstance(result, str)
        assert "GeoJSON" in result

    def test_passes_rag_context_to_prompt(
        self, client: MagicMock, builder: PromptBuilder, retrieved_docs: list
    ) -> None:
        """F1, P4: RAG context passed to PromptBuilder."""
        client.chat.return_value = "answer"

        answer_question(
            user_input="test",
            retrieved_docs=retrieved_docs,
            history=[],
            client=client,
            builder=builder,
        )

        call_args = client.chat.call_args
        system_prompt = call_args.kwargs["system_prompt"]
        assert "ogr2ogr" in system_prompt
        assert "GeoJSON" in system_prompt

    def test_uses_higher_temperature(
        self, client: MagicMock, builder: PromptBuilder, retrieved_docs: list
    ) -> None:
        """F1: Q&A uses temperature=0.3."""
        client.chat.return_value = "answer"

        answer_question(
            user_input="test",
            retrieved_docs=retrieved_docs,
            history=[],
            client=client,
            builder=builder,
        )

        call_args = client.chat.call_args
        assert call_args.kwargs["temperature"] == 0.3

    def test_empty_retrieved_docs(
        self, client: MagicMock, builder: PromptBuilder
    ) -> None:
        """F1: Handles empty retrieval results gracefully."""
        client.chat.return_value = "文档中未提及相关信息。"

        result = answer_question(
            user_input="一个完全无关的问题",
            retrieved_docs=[],
            history=[],
            client=client,
            builder=builder,
        )

        assert isinstance(result, str)

    def test_includes_history(
        self, client: MagicMock, builder: PromptBuilder, retrieved_docs: list
    ) -> None:
        """F1, F8: History messages included."""
        client.chat.return_value = "answer"

        history = [
            Message(role="user", content="之前的问题"),
            Message(role="assistant", content="之前的回答"),
        ]

        answer_question(
            user_input="现在的追问",
            retrieved_docs=retrieved_docs,
            history=history,
            client=client,
            builder=builder,
        )

        call_args = client.chat.call_args
        messages = call_args.kwargs["messages"]
        assert len(messages) == 3
        assert messages[-1].content == "现在的追问"

    def test_user_input_as_last_message(
        self, client: MagicMock, builder: PromptBuilder, retrieved_docs: list
    ) -> None:
        """F1: Current user input is the last message."""
        client.chat.return_value = "answer"

        answer_question(
            user_input="ogr2ogr 能输出 GeoJSON 吗？",
            retrieved_docs=retrieved_docs,
            history=[],
            client=client,
            builder=builder,
        )

        call_args = client.chat.call_args
        messages = call_args.kwargs["messages"]
        assert messages[-1].role == "user"
        assert "GeoJSON" in messages[-1].content
