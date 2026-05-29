"""Config data models.

Design: DC-0002
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class LLMConfig:
    """LLM connection configuration."""

    base_url: str
    auth_key: str
    model_name: str


@dataclass(frozen=True)
class WorkspaceConfig:
    """Workspace default configuration."""

    default_path: str = "."
    allow_parent_access: bool = False


@dataclass(frozen=True)
class APIConfig:
    """FastAPI server configuration."""

    host: str = "0.0.0.0"
    port: int = 8000


@dataclass(frozen=True)
class Config:
    """Global configuration root object."""

    llm: LLMConfig
    workspace: WorkspaceConfig
    api: APIConfig = APIConfig()
