"""Config loader with validation and environment variable overrides.

Design: DC-0001, DC-0003, DC-0004, DC-0005
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from config.models import (
    Config,
    EmbeddingConfig,
    LLMConfig,
    RAGConfig,
    WorkspaceConfig,
)

logger = logging.getLogger(__name__)

# Module-level singleton instance
_config_instance: Optional[Config] = None


def _clear_config_singleton() -> None:
    """Clear the module-level singleton (for testing only)."""
    global _config_instance
    _config_instance = None


def _bool_from_env(value: str) -> bool:
    """Parse a string value from environment variable to bool."""
    return value.lower() in ("true", "1", "yes", "on")


def _apply_env_overrides(raw: dict[str, Any]) -> dict[str, Any]:
    """Apply GISAGENT_* environment variable overrides to raw config dict.

    Mapping rules:
        GISAGENT_LLM_BASE_URL        -> llm.base_url
        GISAGENT_LLM_AUTH_KEY        -> llm.auth_key
        GISAGENT_LLM_MODEL_NAME      -> llm.model_name
        GISAGENT_EMBEDDING_MODEL_PATH -> embedding.model_path
        GISAGENT_EMBEDDING_DEVICE    -> embedding.device
        GISAGENT_RAG_CHUNK_SIZE      -> rag.chunk_size
        GISAGENT_RAG_CHUNK_OVERLAP   -> rag.chunk_overlap
        GISAGENT_RAG_TOP_K           -> rag.top_k
        GISAGENT_WORKSPACE_DEFAULT_PATH        -> workspace.default_path
        GISAGENT_WORKSPACE_ALLOW_PARENT_ACCESS -> workspace.allow_parent_access
    """
    env_map = {
        "GISAGENT_LLM_BASE_URL": ("llm", "base_url", str),
        "GISAGENT_LLM_AUTH_KEY": ("llm", "auth_key", str),
        "GISAGENT_LLM_MODEL_NAME": ("llm", "model_name", str),
        "GISAGENT_EMBEDDING_MODEL_PATH": ("embedding", "model_path", str),
        "GISAGENT_EMBEDDING_DEVICE": ("embedding", "device", str),
        "GISAGENT_RAG_CHUNK_SIZE": ("rag", "chunk_size", int),
        "GISAGENT_RAG_CHUNK_OVERLAP": ("rag", "chunk_overlap", int),
        "GISAGENT_RAG_TOP_K": ("rag", "top_k", int),
        "GISAGENT_WORKSPACE_DEFAULT_PATH": ("workspace", "default_path", str),
        "GISAGENT_WORKSPACE_ALLOW_PARENT_ACCESS": (
            "workspace",
            "allow_parent_access",
            bool,
        ),
    }

    for env_name, (section, key, cast_type) in env_map.items():
        env_value = os.environ.get(env_name)
        if env_value is None:
            continue
        if section not in raw:
            raw[section] = {}
        if cast_type is bool:
            raw[section][key] = _bool_from_env(env_value)
        elif cast_type is int:
            try:
                raw[section][key] = int(env_value)
            except ValueError as exc:
                raise ValueError(
                    f"Environment variable {env_name} must be an integer, "
                    f"got: {env_value!r}"
                ) from exc
        else:
            raw[section][key] = env_value

    return raw


def _validate_config(raw: dict[str, Any]) -> None:
    """Validate raw config dict.

    Raises:
        ValueError: If validation fails.
    """
    missing: list[str] = []

    # --- Section presence ---
    for section in ("llm", "embedding"):
        if section not in raw:
            missing.append(section)
        elif not isinstance(raw[section], dict):
            raise ValueError(f"Config section '{section}' must be an object")

    if missing:
        raise ValueError(f"Missing required config sections: {missing}")

    # --- LLM required fields ---
    llm = raw.get("llm", {})
    for field in ("base_url", "auth_key", "model_name"):
        if field not in llm or not llm[field]:
            missing.append(f"llm.{field}")

    # --- Embedding required fields ---
    embedding = raw.get("embedding", {})
    if "model_path" not in embedding or not embedding["model_path"]:
        missing.append("embedding.model_path")

    if missing:
        raise ValueError(f"Missing required fields: {missing}")

    # --- URL validation ---
    base_url = llm.get("base_url", "")
    if not base_url or not (
        base_url.startswith("http://") or base_url.startswith("https://")
    ):
        raise ValueError(
            f"llm.base_url must be a non-empty URL starting with http:// or https://, "
            f"got: {base_url!r}"
        )

    # --- device validation ---
    device = embedding.get("device", "cpu")
    if device not in ("cpu", "cuda"):
        raise ValueError(f"embedding.device must be 'cpu' or 'cuda', got: {device!r}")

    # Note: model_path existence is checked at runtime by the retriever
    # rather than at config load time, because the path may be resolved
    # dynamically (e.g. HuggingFace cache structure).

    # --- RAG defaults & validation ---
    rag = raw.get("rag", {})
    chunk_size = rag.get("chunk_size", 512)
    chunk_overlap = rag.get("chunk_overlap", 128)

    for name, value in (("chunk_size", chunk_size), ("chunk_overlap", chunk_overlap)):
        if not isinstance(value, int):
            raise ValueError(f"rag.{name} must be an integer, got: {value!r}")

    if chunk_size <= 0:
        raise ValueError(f"rag.chunk_size must be > 0, got: {chunk_size}")

    if chunk_overlap < 0:
        raise ValueError(f"rag.chunk_overlap must be >= 0, got: {chunk_overlap}")

    if chunk_overlap >= chunk_size:
        raise ValueError(
            f"rag.chunk_overlap ({chunk_overlap}) must be < "
            f"rag.chunk_size ({chunk_size})"
        )

    top_k = rag.get("top_k", 5)
    if not isinstance(top_k, int) or top_k <= 0:
        raise ValueError(f"rag.top_k must be > 0, got: {top_k!r}")

    # --- Workspace defaults ---
    workspace = raw.get("workspace", {})
    default_path = workspace.get("default_path", ".")
    if not default_path:
        raise ValueError("workspace.default_path must be non-empty")

    allow_parent = workspace.get("allow_parent_access", False)
    if not isinstance(allow_parent, bool):
        raise ValueError(
            f"workspace.allow_parent_access must be a boolean, got: {allow_parent!r}"
        )


def _fill_defaults(raw: dict[str, Any]) -> dict[str, Any]:
    """Fill in default values for optional fields."""
    if "rag" not in raw:
        raw["rag"] = {}
    rag = raw["rag"]
    rag.setdefault("chunk_size", 512)
    rag.setdefault("chunk_overlap", 128)
    rag.setdefault("top_k", 5)

    if "workspace" not in raw:
        raw["workspace"] = {}
    workspace = raw["workspace"]
    workspace.setdefault("default_path", ".")
    workspace.setdefault("allow_parent_access", False)

    embedding = raw.setdefault("embedding", {})
    embedding.setdefault("device", "cpu")

    return raw


def _build_config(raw: dict[str, Any]) -> Config:
    """Construct Config dataclass from validated raw dict."""
    return Config(
        llm=LLMConfig(
            base_url=raw["llm"]["base_url"],
            auth_key=raw["llm"]["auth_key"],
            model_name=raw["llm"]["model_name"],
        ),
        embedding=EmbeddingConfig(
            model_path=raw["embedding"]["model_path"],
            device=raw["embedding"].get("device", "cpu"),
        ),
        rag=RAGConfig(
            chunk_size=raw["rag"].get("chunk_size", 512),
            chunk_overlap=raw["rag"].get("chunk_overlap", 128),
            top_k=raw["rag"].get("top_k", 5),
        ),
        workspace=WorkspaceConfig(
            default_path=raw["workspace"].get("default_path", "."),
            allow_parent_access=raw["workspace"].get("allow_parent_access", False),
        ),
    )


def load_config(path: Optional[Path] = None) -> Config:
    """Load and validate config file, initialize global singleton.

    Args:
        path: Config file path. Defaults to SourceCode/config/config.json
              relative to the project root.

    Returns:
        Validated Config object.

    Raises:
        FileNotFoundError: Config file does not exist.
        json.JSONDecodeError: Invalid JSON format.
        ValueError: Missing required fields or type mismatch.

    Design: DC-0001, DC-0003, DC-0004, DC-0005
    """
    global _config_instance

    if path is None:
        # Default: SourceCode/config/config.json relative to project root
        path = (
            Path(__file__).parent.parent.parent.parent
            / "SourceCode"
            / "config"
            / "config.json"
        )

    path = Path(path)

    if not path.exists():
        logger.error("Config file not found: %s", path)
        raise FileNotFoundError(f"Config file not found: {path}")

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Failed to read config file: %s", exc)
        raise

    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON in config file %s: %s", path, exc)
        raise

    if not isinstance(raw, dict):
        raise ValueError("Config file must contain a JSON object")

    # Apply environment variable overrides
    raw = _apply_env_overrides(raw)

    # Fill defaults before validation so optional sections have sensible values
    raw = _fill_defaults(raw)

    # Validate
    try:
        _validate_config(raw)
    except ValueError as exc:
        logger.error("Config validation failed: %s", exc)
        raise

    # Build immutable Config object
    config = _build_config(raw)
    _config_instance = config
    return config


def get_config() -> Config:
    """Get the loaded global config instance.

    Returns:
        Config singleton.

    Raises:
        RuntimeError: Called before load_config().

    Design: DC-0005
    """
    if _config_instance is None:
        raise RuntimeError("Config not loaded. Call load_config() before get_config().")
    return _config_instance
