"""GIS Agent global configuration module.

Public API:
    load_config(path) -> Config
    get_config() -> Config

Data models:
    Config, LLMConfig, EmbeddingConfig, RAGConfig, WorkspaceConfig

Design: plan-config v1.0.0
"""

from src.config.loader import get_config, load_config
from src.config.models import (
    Config,
    EmbeddingConfig,
    LLMConfig,
    RAGConfig,
    WorkspaceConfig,
)

__all__ = [
    "Config",
    "EmbeddingConfig",
    "LLMConfig",
    "RAGConfig",
    "WorkspaceConfig",
    "get_config",
    "load_config",
]
