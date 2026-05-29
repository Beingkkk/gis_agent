"""GIS Agent global configuration module.

Public API:
    load_config(path) -> Config
    get_config() -> Config

Data models:
    Config, LLMConfig, WorkspaceConfig

Design: plan-config v1.0.0
"""

from config.loader import get_config, load_config
from config.models import Config, LLMConfig, WorkspaceConfig

__all__ = [
    "Config",
    "LLMConfig",
    "WorkspaceConfig",
    "get_config",
    "load_config",
]
