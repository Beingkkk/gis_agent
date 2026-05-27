"""Tests for rag.retriever module.

Design: DC-0021, DC-0022, DC-0023, DC-0024
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import rag.retriever
from rag.preprocess import DocumentChunk
from rag.retriever import (
    DocumentRetriever,
    RetrievedDocument,
    _resolve_embedding_model_path,
    get_retriever,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_chunks_json(tmp_path: Path) -> Path:
    """Create a sample chunks JSON file for testing."""
    data = {
        "version": "1.0.0",
        "source": "Test",
        "generated_at": "2026-05-27",
        "chunks": [
            {
                "id": "ogr2ogr-001",
                "source_file": "programs/ogr2ogr.html",
                "title": "ogr2ogr",
                "section": "Synopsis",
                "content": "Usage: ogr2ogr [--help] [--long-usage]",
                "token_estimate": 32,
            },
            {
                "id": "ogr2ogr-002",
                "source_file": "programs/ogr2ogr.html",
                "title": "ogr2ogr",
                "section": "Description",
                "content": "Converts simple features data between file formats.",
                "token_estimate": 16,
            },
        ],
    }
    path = tmp_path / "gdal-docs-chunks.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# RetrievedDocument tests
# ---------------------------------------------------------------------------


class TestRetrievedDocument:
    """Tests for RetrievedDocument dataclass."""

    def test_creation(self) -> None:
        chunk = DocumentChunk(
            id="test-001",
            source_file="test.html",
            title="Test",
            section="Usage",
            content="Test content",
            token_estimate=10,
        )
        doc = RetrievedDocument(chunk=chunk, distance=0.5)
        assert doc.chunk.id == "test-001"
        assert doc.distance == 0.5


# ---------------------------------------------------------------------------
# DocumentRetriever initialization tests
# ---------------------------------------------------------------------------


class TestDocumentRetrieverInit:
    """Tests for DocumentRetriever.__init__."""

    def test_init_defaults(self, tmp_path: Path) -> None:
        retriever = DocumentRetriever(
            chunks_json_path=tmp_path / "chunks.json",
            embedding_model_path="/fake/model",
            cache_dir=tmp_path / "cache",
        )
        assert retriever.collection_name == "gdal_docs"
        assert retriever.top_k == 5
        assert not retriever.is_ready()

    def test_init_custom_params(self, tmp_path: Path) -> None:
        retriever = DocumentRetriever(
            collection_name="custom",
            chunks_json_path=tmp_path / "c.json",
            embedding_model_path="/fake",
            cache_dir=tmp_path / "cache",
            top_k=10,
        )
        assert retriever.collection_name == "custom"
        assert retriever.top_k == 10


# ---------------------------------------------------------------------------
# DocumentRetriever _load_or_build_index tests
# ---------------------------------------------------------------------------


class TestLoadOrBuildIndex:
    """Tests for DocumentRetriever._load_or_build_index."""

    def test_missing_json_raises(self, tmp_path: Path) -> None:
        retriever = DocumentRetriever(
            chunks_json_path=tmp_path / "nonexistent.json",
            embedding_model_path="/fake",
            cache_dir=tmp_path / "cache",
        )
        with pytest.raises(FileNotFoundError):
            retriever._load_or_build_index()

    @patch("rag.retriever.SentenceTransformer")
    @patch("rag.retriever.chromadb.PersistentClient")
    def test_builds_index_on_first_run(
        self,
        mock_client_cls: MagicMock,
        mock_st_cls: MagicMock,
        sample_chunks_json: Path,
        tmp_path: Path,
    ) -> None:
        mock_model = MagicMock()
        arr = MagicMock()
        arr.tolist.return_value = [[0.1] * 384, [0.2] * 384]
        mock_model.encode.return_value = arr
        mock_st_cls.return_value = mock_model

        mock_collection = MagicMock()
        mock_client = MagicMock()
        mock_client.create_collection.return_value = mock_collection
        mock_client.delete_collection.return_value = None
        mock_client_cls.return_value = mock_client

        retriever = DocumentRetriever(
            chunks_json_path=sample_chunks_json,
            embedding_model_path="/fake/model",
            cache_dir=tmp_path / "cache",
        )
        retriever._load_or_build_index()

        assert retriever.is_ready()
        mock_st_cls.assert_called_once_with("/fake/model", device="cpu")
        mock_client.create_collection.assert_called_once_with("gdal_docs")
        assert mock_collection.add.call_count == 1

    @patch("rag.retriever.SentenceTransformer")
    @patch("rag.retriever.chromadb.PersistentClient")
    def test_uses_cache_on_hash_match(
        self,
        mock_client_cls: MagicMock,
        mock_st_cls: MagicMock,
        sample_chunks_json: Path,
        tmp_path: Path,
    ) -> None:
        # First run: build
        mock_model = MagicMock()
        arr = MagicMock()
        arr.tolist.return_value = [[0.1] * 384, [0.2] * 384]
        mock_model.encode.return_value = arr
        mock_st_cls.return_value = mock_model

        mock_collection = MagicMock()
        mock_client = MagicMock()
        mock_client.create_collection.return_value = mock_collection
        mock_client.delete_collection.return_value = None
        mock_client_cls.return_value = mock_client

        retriever = DocumentRetriever(
            chunks_json_path=sample_chunks_json,
            embedding_model_path="/fake/model",
            cache_dir=tmp_path / "cache",
        )
        retriever._load_or_build_index()
        assert retriever.is_ready()

        # Second run: should use cache
        mock_client.reset_mock()
        mock_client.get_collection.return_value = mock_collection

        retriever2 = DocumentRetriever(
            chunks_json_path=sample_chunks_json,
            embedding_model_path="/fake/model",
            cache_dir=tmp_path / "cache",
        )
        retriever2._load_or_build_index()

        assert retriever2.is_ready()
        mock_client.get_collection.assert_called_once_with("gdal_docs")
        mock_client.create_collection.assert_not_called()

    @patch("rag.retriever.SentenceTransformer")
    def test_model_load_failure_raises(
        self, mock_st_cls: MagicMock, sample_chunks_json: Path, tmp_path: Path
    ) -> None:
        mock_st_cls.side_effect = ImportError("No module named torch")

        retriever = DocumentRetriever(
            chunks_json_path=sample_chunks_json,
            embedding_model_path="/bad/model",
            cache_dir=tmp_path / "cache",
        )
        with pytest.raises(RuntimeError, match="Failed to load embedding model"):
            retriever._load_or_build_index()


# ---------------------------------------------------------------------------
# DocumentRetriever search tests
# ---------------------------------------------------------------------------


class TestSearch:
    """Tests for DocumentRetriever.search."""

    @patch("rag.retriever.SentenceTransformer")
    @patch("rag.retriever.chromadb.PersistentClient")
    def test_search_returns_results(
        self,
        mock_client_cls: MagicMock,
        mock_st_cls: MagicMock,
        sample_chunks_json: Path,
        tmp_path: Path,
    ) -> None:
        mock_model = MagicMock()
        arr = MagicMock()
        arr.tolist.return_value = [[0.1] * 384, [0.2] * 384]
        mock_model.encode.return_value = arr
        mock_st_cls.return_value = mock_model

        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "ids": [["ogr2ogr-001", "ogr2ogr-002"]],
            "distances": [[0.3, 0.7]],
            "metadatas": [
                [
                    {
                        "source_file": "p1.html",
                        "title": "t1",
                        "section": "s1",
                    },
                    {
                        "source_file": "p2.html",
                        "title": "t2",
                        "section": "s2",
                    },
                ]
            ],
            "documents": [["doc1", "doc2"]],
        }

        mock_client = MagicMock()
        mock_client.create_collection.return_value = mock_collection
        mock_client.delete_collection.return_value = None
        mock_client_cls.return_value = mock_client

        retriever = DocumentRetriever(
            chunks_json_path=sample_chunks_json,
            embedding_model_path="/fake/model",
            cache_dir=tmp_path / "cache",
        )
        retriever._load_or_build_index()

        # Change encode return for query
        query_arr = MagicMock()
        query_arr.tolist.return_value = [[0.15] * 384]
        mock_model.encode.return_value = query_arr

        results = retriever.search("ogr2ogr geojson", top_k=2)

        assert len(results) == 2
        assert results[0].chunk.id == "ogr2ogr-001"
        assert results[0].distance == 0.3
        assert results[0].chunk.content == "doc1"
        assert results[1].chunk.id == "ogr2ogr-002"
        assert results[1].distance == 0.7

        mock_collection.query.assert_called_once_with(
            query_embeddings=[[0.15] * 384],
            n_results=2,
        )

    def test_search_before_ready_raises(self, tmp_path: Path) -> None:
        retriever = DocumentRetriever(
            chunks_json_path=tmp_path / "fake.json",
            embedding_model_path="/fake",
            cache_dir=tmp_path / "cache",
        )
        with pytest.raises(RuntimeError, match="not ready"):
            retriever.search("query")

    @patch("rag.retriever.SentenceTransformer")
    @patch("rag.retriever.chromadb.PersistentClient")
    def test_search_empty_results(
        self,
        mock_client_cls: MagicMock,
        mock_st_cls: MagicMock,
        sample_chunks_json: Path,
        tmp_path: Path,
    ) -> None:
        mock_model = MagicMock()
        arr = MagicMock()
        arr.tolist.return_value = [[0.1] * 384, [0.2] * 384]
        mock_model.encode.return_value = arr
        mock_st_cls.return_value = mock_model

        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "ids": [[]],
            "distances": [[]],
            "metadatas": [[]],
            "documents": [[]],
        }

        mock_client = MagicMock()
        mock_client.create_collection.return_value = mock_collection
        mock_client.delete_collection.return_value = None
        mock_client_cls.return_value = mock_client

        retriever = DocumentRetriever(
            chunks_json_path=sample_chunks_json,
            embedding_model_path="/fake/model",
            cache_dir=tmp_path / "cache",
        )
        retriever._load_or_build_index()

        query_arr = MagicMock()
        query_arr.tolist.return_value = [[0.15] * 384]
        mock_model.encode.return_value = query_arr

        results = retriever.search("nonsense query")
        assert results == []

    @patch("rag.retriever.SentenceTransformer")
    @patch("rag.retriever.chromadb.PersistentClient")
    def test_search_uses_default_top_k(
        self,
        mock_client_cls: MagicMock,
        mock_st_cls: MagicMock,
        sample_chunks_json: Path,
        tmp_path: Path,
    ) -> None:
        mock_model = MagicMock()
        arr = MagicMock()
        arr.tolist.return_value = [[0.1] * 384, [0.2] * 384]
        mock_model.encode.return_value = arr
        mock_st_cls.return_value = mock_model

        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "ids": [[]],
            "distances": [[]],
            "metadatas": [[]],
            "documents": [[]],
        }

        mock_client = MagicMock()
        mock_client.create_collection.return_value = mock_collection
        mock_client.delete_collection.return_value = None
        mock_client_cls.return_value = mock_client

        retriever = DocumentRetriever(
            chunks_json_path=sample_chunks_json,
            embedding_model_path="/fake/model",
            cache_dir=tmp_path / "cache",
            top_k=5,
        )
        retriever._load_or_build_index()

        query_arr = MagicMock()
        query_arr.tolist.return_value = [[0.15] * 384]
        mock_model.encode.return_value = query_arr

        retriever.search("query")
        _, kwargs = mock_collection.query.call_args
        assert kwargs["n_results"] == 5


# ---------------------------------------------------------------------------
# get_retriever tests
# ---------------------------------------------------------------------------


class TestGetRetriever:
    """Tests for get_retriever singleton."""

    def test_returns_same_instance(self, tmp_path: Path) -> None:
        with patch.object(rag.retriever, "_retriever_instance", None):
            with patch.object(DocumentRetriever, "_load_or_build_index"):
                r1 = get_retriever(
                    chunks_json_path=tmp_path / "c.json",
                    embedding_model_path="/fake",
                    cache_dir=tmp_path / "cache",
                )
                r2 = get_retriever(
                    chunks_json_path=tmp_path / "c.json",
                    embedding_model_path="/fake",
                    cache_dir=tmp_path / "cache",
                )
                assert r1 is r2

    def test_singleton_ignores_subsequent_params(self, tmp_path: Path) -> None:
        with patch.object(rag.retriever, "_retriever_instance", None):
            with patch.object(DocumentRetriever, "_load_or_build_index"):
                r1 = get_retriever(
                    chunks_json_path=tmp_path / "c.json",
                    embedding_model_path="/fake",
                    cache_dir=tmp_path / "cache",
                    top_k=5,
                )
                r2 = get_retriever(
                    chunks_json_path=tmp_path / "d.json",
                    embedding_model_path="/other",
                    cache_dir=tmp_path / "other",
                    top_k=10,
                )
                assert r1 is r2
                assert r1.top_k == 5


# ---------------------------------------------------------------------------
# _resolve_embedding_model_path tests
# ---------------------------------------------------------------------------


class TestResolveModelPath:
    """Tests for _resolve_embedding_model_path."""

    def test_embedding_path(self, tmp_path: Path) -> None:
        model_dir = tmp_path / "SourceCode" / "model" / "embedding"
        model_dir.mkdir(parents=True)
        result = _resolve_embedding_model_path(tmp_path)
        assert result == str(model_dir)

    def test_not_found_raises(self, tmp_path: Path) -> None:
        with pytest.raises(RuntimeError, match="not found"):
            _resolve_embedding_model_path(tmp_path)


# ---------------------------------------------------------------------------
# _compute_file_hash tests
# ---------------------------------------------------------------------------


class TestComputeFileHash:
    """Tests for DocumentRetriever._compute_file_hash."""

    def test_hash_consistency(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world", encoding="utf-8")

        h1 = DocumentRetriever._compute_file_hash(test_file)
        h2 = DocumentRetriever._compute_file_hash(test_file)
        assert h1 == h2
        assert len(h1) == 64  # sha256 hex

    def test_hash_changes_with_content(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.txt"
        f1.write_text("content A", encoding="utf-8")
        f2 = tmp_path / "b.txt"
        f2.write_text("content B", encoding="utf-8")

        h1 = DocumentRetriever._compute_file_hash(f1)
        h2 = DocumentRetriever._compute_file_hash(f2)
        assert h1 != h2
