"""Config data models.

Uses pydantic BaseModel for automatic validation and immutability.
Environment variable overrides are applied via model_validator.

Design: DC-0002, ADR-0004
"""

import os
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LLMConfig(BaseModel):
    """LLM connection configuration."""

    model_config = ConfigDict(frozen=True)
    base_url: str = Field(
        ...,
        pattern=r"^https?://",
        description="LLM API base URL",
    )
    auth_key: str = Field(
        ...,
        min_length=1,
        description="LLM API authentication key",
    )
    model_name: str = Field(
        ...,
        min_length=1,
        description="LLM model name",
    )


class Config(BaseModel):
    """Global configuration root object."""

    model_config = ConfigDict(frozen=True)
    llm: LLMConfig

    @model_validator(mode="before")
    @classmethod
    def _apply_env_overrides(cls, data: Any) -> Any:
        """Apply GISAGENT_* environment variable overrides.

        Maps GISAGENT_LLM_BASE_URL → llm.base_url, etc.
        Environment variables take precedence over JSON file values.

        Design: DC-0003, ADR-0004
        """
        if isinstance(data, dict):
            llm = dict(data.get("llm", {}))
            for key in ("base_url", "auth_key", "model_name"):
                env_name = f"GISAGENT_LLM_{key.upper()}"
                env_val = os.environ.get(env_name)
                if env_val is not None:
                    llm[key] = env_val
            data = dict(data)
            data["llm"] = llm
        return data
