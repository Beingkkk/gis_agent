"""Config data models.

Design: DC-0002
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class LLMConfig:
    """LLM connection configuration."""

    base_url: str
    auth_key: str
    model_name: str


@dataclass(frozen=True)
class EmbeddingConfig:
    """Embedding model configuration."""

    model_path: str
    device: Literal["cpu", "cuda"] = "cpu"


@dataclass(frozen=True)
class RAGConfig:
    """RAG retrieval configuration."""

    chunk_size: int = 512
    chunk_overlap: int = 128
    top_k: int = 5


@dataclass(frozen=True)
class WorkspaceConfig:
    """Workspace default configuration."""

    default_path: str = "."
    allow_parent_access: bool = False


@dataclass(frozen=True)
class Config:
    """Global configuration root object."""

    llm: LLMConfig
    embedding: EmbeddingConfig
    rag: RAGConfig
    workspace: WorkspaceConfig
