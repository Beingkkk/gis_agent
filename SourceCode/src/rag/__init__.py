"""RAG module — GDAL document retrieval.

Public API:
    DocumentRetriever, RetrievedDocument, get_retriever

Preprocess (development only):
    preprocess.preprocess_directory()

Design: plan-rag v1.0.1
"""

from rag.retriever import DocumentRetriever, RetrievedDocument, get_retriever

__all__ = ["DocumentRetriever", "RetrievedDocument", "get_retriever"]
