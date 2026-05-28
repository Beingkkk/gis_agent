"""Unit tests for DocumentRetriever.search_multi().

Design: plan-qa-optimization v1.0.0
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rag.preprocess import DocumentChunk
from rag.retriever import DocumentRetriever, RetrievedDocument


class TestSearchMulti:
    """Multi-query retrieval with deduplication and ranking."""

    @pytest.fixture
    def ready_retriever(self, tmp_path: Path) -> DocumentRetriever:
        """Retriever with _ready=True and mocked internals."""
        retriever = DocumentRetriever(
            collection_name="test",
            chunks_json_path=tmp_path / "chunks.json",
            embedding_model_path="dummy",
            cache_dir=tmp_path / "cache",
            top_k=3,
        )
        retriever._ready = True
        retriever._embedding_model = MagicMock()
        retriever._collection = MagicMock()
        return retriever

    def _make_doc(
        self, doc_id: str, content: str, distance: float
    ) -> RetrievedDocument:
        """Factory for RetrievedDocument."""
        chunk = DocumentChunk(
            id=doc_id,
            source_file="test.html",
            title="Test",
            section="section",
            content=content,
            token_estimate=len(content) // 4,
        )
        return RetrievedDocument(chunk=chunk, distance=distance)

    def test_single_query_equivalent_to_search(
        self, ready_retriever: DocumentRetriever
    ) -> None:
        """search_multi with one query should match search behavior."""
        doc = self._make_doc("c1", "content", 0.1)

        with patch.object(ready_retriever, "search", return_value=[doc]) as mock_search:
            result = ready_retriever.search_multi(["query1"], top_k_per_query=2)

        mock_search.assert_called_once_with("query1", top_k=2)
        assert len(result) == 1
        assert result[0].chunk.id == "c1"

    def test_merge_results_from_multiple_queries(
        self, ready_retriever: DocumentRetriever
    ) -> None:
        """Multiple queries: results merged."""
        doc1 = self._make_doc("c1", "a", 0.1)
        doc2 = self._make_doc("c2", "b", 0.2)

        def side_effect(query: str, top_k: int) -> list[RetrievedDocument]:
            if query == "q1":
                return [doc1]
            return [doc2]

        with patch.object(ready_retriever, "search", side_effect=side_effect):
            result = ready_retriever.search_multi(["q1", "q2"])

        assert len(result) == 2
        ids = {r.chunk.id for r in result}
        assert ids == {"c1", "c2"}

    def test_deduplicate_by_chunk_id(self, ready_retriever: DocumentRetriever) -> None:
        """Overlapping results: deduplicated by chunk id."""
        doc1 = self._make_doc("c1", "a", 0.1)
        doc2 = self._make_doc("c1", "a", 0.2)  # same id

        def side_effect(query: str, top_k: int) -> list[RetrievedDocument]:
            if query == "q1":
                return [doc1]
            return [doc2]

        with patch.object(ready_retriever, "search", side_effect=side_effect):
            result = ready_retriever.search_multi(["q1", "q2"])

        assert len(result) == 1
        assert result[0].distance == 0.1  # lower distance wins

    def test_sort_by_distance_ascending(
        self, ready_retriever: DocumentRetriever
    ) -> None:
        """Final result sorted by distance ascending."""
        doc_high = self._make_doc("c1", "a", 0.5)
        doc_low = self._make_doc("c2", "b", 0.1)
        doc_mid = self._make_doc("c3", "c", 0.3)

        def side_effect(query: str, top_k: int) -> list[RetrievedDocument]:
            return {"q1": [doc_high], "q2": [doc_low], "q3": [doc_mid]}[query]

        with patch.object(ready_retriever, "search", side_effect=side_effect):
            result = ready_retriever.search_multi(["q1", "q2", "q3"])

        distances = [r.distance for r in result]
        assert distances == [0.1, 0.3, 0.5]

    def test_keep_lower_distance_on_conflict(
        self, ready_retriever: DocumentRetriever
    ) -> None:
        """When same chunk has different distances, keep the lower one."""
        doc_better = self._make_doc("c1", "a", 0.1)
        doc_worse = self._make_doc("c1", "a", 0.5)

        def side_effect(query: str, top_k: int) -> list[RetrievedDocument]:
            return [doc_worse] if query == "q1" else [doc_better]

        with patch.object(ready_retriever, "search", side_effect=side_effect):
            result = ready_retriever.search_multi(["q1", "q2"])

        assert len(result) == 1
        assert result[0].distance == 0.1

    def test_empty_queries_returns_empty(
        self, ready_retriever: DocumentRetriever
    ) -> None:
        """Empty query list returns empty results."""
        with patch.object(ready_retriever, "search") as mock_search:
            result = ready_retriever.search_multi([])

        mock_search.assert_not_called()
        assert result == []

    def test_not_ready_raises(self, tmp_path: Path) -> None:
        """search_multi requires ready state."""
        retriever = DocumentRetriever(
            collection_name="test",
            chunks_json_path=tmp_path / "chunks.json",
            embedding_model_path="dummy",
            cache_dir=tmp_path / "cache",
        )
        # _ready is False by default
        with pytest.raises(RuntimeError, match="not ready"):
            retriever.search_multi(["q1"])

    def test_uses_default_top_k_when_not_specified(
        self, ready_retriever: DocumentRetriever
    ) -> None:
        """search_multi without top_k_per_query passes None to search."""
        doc = self._make_doc("c1", "a", 0.1)

        with patch.object(ready_retriever, "search", return_value=[doc]) as mock_search:
            ready_retriever.search_multi(["q1"])

        mock_search.assert_called_once_with("q1", top_k=None)
