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
class Config:
    """Global configuration root object."""

    llm: LLMConfig
