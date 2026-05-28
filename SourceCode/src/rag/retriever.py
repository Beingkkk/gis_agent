"""RAG retriever with ChromaDB integration.

Public API:
    DocumentRetriever, RetrievedDocument, get_retriever

Design: DC-0021, DC-0022, DC-0023, DC-0024
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

import chromadb
from chromadb.config import Settings

from rag.preprocess import DocumentChunk

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None  # type: ignore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetrievedDocument:
    """A retrieved document with relevance score.

    Design: DC-0021
    """

    chunk: DocumentChunk
    distance: float  # ChromaDB L2 distance; smaller = more relevant


class DocumentRetriever:
    """GDAL document vector retriever.

    Encapsulates ChromaDB initialization, index building, and semantic search.
    Process-level singleton; accessed via get_retriever().

    Design: DC-0021, DC-0022, DC-0023, DC-0024
    """

    def __init__(
        self,
        *,
        collection_name: str = "gdal_docs",
        chunks_json_path: Path,
        embedding_model_path: str,
        cache_dir: Path,
        top_k: int = 5,
    ) -> None:
        self.collection_name = collection_name
        self.chunks_json_path = Path(chunks_json_path)
        self.embedding_model_path = embedding_model_path
        self.cache_dir = Path(cache_dir)
        self.top_k = top_k
        self._client: Optional[Any] = None
        self._collection: Optional[Any] = None
        self._embedding_model: Optional[Any] = None
        self._ready = False

    def is_ready(self) -> bool:
        """Whether the index is ready for search."""
        return self._ready

    def search(
        self, query: str, top_k: Optional[int] = None
    ) -> List[RetrievedDocument]:
        """Semantic search for relevant GDAL document chunks.

        Args:
            query: User query (Chinese or English).
            top_k: Number of results. Defaults to self.top_k.

        Returns:
            List of RetrievedDocument sorted by relevance
            (distance ascending).

        Raises:
            RuntimeError: If index is not ready.
        """
        if not self._ready:
            raise RuntimeError(
                "Retriever not ready. Index must be loaded before search."
            )

        assert self._embedding_model is not None
        assert self._collection is not None

        k = top_k or self.top_k
        query_embedding = self._embedding_model.encode([query]).tolist()

        results = self._collection.query(
            query_embeddings=query_embedding,
            n_results=k,
        )

        retrieved: List[RetrievedDocument] = []
        ids_list = results.get("ids", [[]])[0]
        if not ids_list:
            return retrieved

        distances_list = results.get("distances", [[]])[0]
        metadatas_list = results.get("metadatas", [[]])[0]
        documents_list = results.get("documents", [[]])[0]

        for i, chunk_id in enumerate(ids_list):
            metadata = metadatas_list[i] if metadatas_list else {}
            distance = distances_list[i] if distances_list else 0.0
            document = documents_list[i] if documents_list else ""

            chunk = DocumentChunk(
                id=chunk_id,
                source_file=metadata.get("source_file", ""),
                title=metadata.get("title", ""),
                section=metadata.get("section", ""),
                content=document,
                token_estimate=max(1, len(document) // 4),
            )
            retrieved.append(RetrievedDocument(chunk=chunk, distance=distance))

        return retrieved

    def search_multi(
        self,
        queries: List[str],
        top_k_per_query: Optional[int] = None,
    ) -> List[RetrievedDocument]:
        """Multi-query retrieval with deduplication and relevance ranking.

        Runs each query through semantic search, merges results, deduplicates
        by chunk id (keeping the most relevant distance), and sorts by
        distance ascending.

        Args:
            queries: List of search queries (keywords/phrases).
            top_k_per_query: Number of results per query. Defaults to
                self.top_k.

        Returns:
            Deduplicated RetrievedDocument list sorted by distance ascending.

        Raises:
            RuntimeError: If index is not ready.
        """
        if not self._ready:
            raise RuntimeError(
                "Retriever not ready. Index must be loaded before search."
            )

        merged: dict[str, RetrievedDocument] = {}
        for query in queries:
            docs = self.search(query, top_k=top_k_per_query)
            for doc in docs:
                chunk_id = doc.chunk.id
                if chunk_id not in merged or doc.distance < merged[chunk_id].distance:
                    merged[chunk_id] = doc

        return sorted(merged.values(), key=lambda d: d.distance)

    def _load_or_build_index(self) -> None:
        """Initialize or load the ChromaDB index.

        Checks the chunks JSON hash against cached hash. Rebuilds index
        if hash mismatches or no cache exists.

        Raises:
            FileNotFoundError: If chunks JSON file is missing.
            RuntimeError: If model loading or ChromaDB init fails.
        """
        if not self.chunks_json_path.exists():
            raise FileNotFoundError(f"Chunks JSON not found: {self.chunks_json_path}")

        # Load embedding model (always needed for search)
        if SentenceTransformer is None:
            raise RuntimeError(
                "sentence-transformers not installed. Install it to use the retriever."
            )
        try:
            self._embedding_model = SentenceTransformer(
                self.embedding_model_path, device="cpu"
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load embedding model "
                f"from {self.embedding_model_path}: {exc}"
            ) from exc

        current_hash = self._compute_file_hash(self.chunks_json_path)
        hash_file = self.cache_dir / "chunks_hash.txt"

        # Initialize ChromaDB persistent client
        try:
            self._client = chromadb.PersistentClient(
                path=str(self.cache_dir / "chroma"),
                settings=Settings(anonymized_telemetry=False),
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to initialize ChromaDB: {exc}") from exc

        # Check cache
        need_rebuild = True
        if hash_file.exists():
            cached_hash = hash_file.read_text().strip()
            if cached_hash == current_hash:
                need_rebuild = False
                logger.info("ChromaDB cache hit, loading existing collection")

        if need_rebuild:
            logger.info("ChromaDB cache miss, rebuilding index")
            try:
                self._client.delete_collection(self.collection_name)
            except Exception:
                pass

            self._collection = self._client.create_collection(self.collection_name)
            chunks = self._read_chunks()
            self._build_index(chunks)

            self.cache_dir.mkdir(parents=True, exist_ok=True)
            hash_file.write_text(current_hash)
            logger.info("Index rebuilt with %d chunks", len(chunks))
        else:
            self._collection = self._client.get_collection(self.collection_name)

        self._ready = True

    @staticmethod
    def _compute_file_hash(path: Path) -> str:
        """Compute SHA-256 hash of a file.

        Args:
            path: File to hash.

        Returns:
            Hex digest string.
        """
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _read_chunks(self) -> List[dict[str, Any]]:
        """Read chunks from JSON file.

        Returns:
            List of chunk dicts.
        """
        with open(self.chunks_json_path, "r", encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
        chunks: List[dict[str, Any]] = data.get("chunks", [])
        return chunks

    def _build_index(self, chunks: List[dict[str, Any]]) -> None:
        """Build ChromaDB index from chunks.

        Processes chunks in batches to avoid memory issues.

        Args:
            chunks: List of chunk dicts from JSON.
        """
        assert self._embedding_model is not None
        assert self._collection is not None

        batch_size = 100
        total = len(chunks)

        for i in range(0, total, batch_size):
            batch = chunks[i : i + batch_size]
            ids = [c["id"] for c in batch]
            documents = [c["content"] for c in batch]
            metadatas = [
                {
                    "source_file": c.get("source_file", ""),
                    "title": c.get("title", ""),
                    "section": c.get("section", ""),
                }
                for c in batch
            ]

            embeddings = self._embedding_model.encode(documents).tolist()

            self._collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
            )


# Module-level singleton
_retriever_instance: Optional[DocumentRetriever] = None


def get_retriever(
    *,
    collection_name: str = "gdal_docs",
    chunks_json_path: Optional[Path] = None,
    embedding_model_path: Optional[str] = None,
    cache_dir: Optional[Path] = None,
    top_k: int = 5,
) -> DocumentRetriever:
    """Get the global DocumentRetriever singleton.

    First call initializes the retriever by loading or building the index.
    Subsequent calls return the cached instance.

    Args:
        collection_name: ChromaDB collection name.
        chunks_json_path: Path to gdal-docs-chunks.json.
        embedding_model_path: Path to embedding model.
        cache_dir: ChromaDB cache directory.
        top_k: Default number of results.

    Returns:
        Initialized DocumentRetriever.

    Raises:
        RuntimeError: If initialization fails.
    """
    global _retriever_instance
    if _retriever_instance is None:
        project_root = Path(__file__).parent.parent.parent.parent

        if chunks_json_path is None:
            chunks_json_path = (
                project_root / "SourceCode" / "data" / "gdal-docs-chunks.json"
            )

        if embedding_model_path is None:
            embedding_model_path = _resolve_embedding_model_path(project_root)

        if cache_dir is None:
            cache_dir = Path.home() / ".cache" / "gis-agent" / "chroma"

        _retriever_instance = DocumentRetriever(
            collection_name=collection_name,
            chunks_json_path=chunks_json_path,
            embedding_model_path=embedding_model_path,
            cache_dir=cache_dir,
            top_k=top_k,
        )
        _retriever_instance._load_or_build_index()

    return _retriever_instance


def _resolve_embedding_model_path(project_root: Path) -> str:
    """Resolve embedding model path from project structure.

    Expects the model to be in SourceCode/model/embedding/.

    Args:
        project_root: Project root directory.

    Returns:
        Absolute path to the model directory.

    Raises:
        RuntimeError: If model cannot be found.
    """
    model_dir = project_root / "SourceCode" / "model" / "embedding"
    if model_dir.exists():
        return str(model_dir)

    raise RuntimeError(
        f"Embedding model not found at {model_dir}. "
        "Run SourceCode/model/download_embedding.cmd to download it."
    )
