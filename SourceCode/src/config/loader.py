"""Config loader with validation and environment variable overrides.

Uses pydantic for automatic field validation and nested model construction.

Design: DC-0001, DC-0003, DC-0004, DC-0005, ADR-0004
"""

import json
import logging
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from config.models import Config

logger = logging.getLogger(__name__)

# Module-level singleton instance
_config_instance: Optional[Config] = None


def _clear_config_singleton() -> None:
    """Clear the module-level singleton (for testing only)."""
    global _config_instance
    _config_instance = None


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
        ValueError: Validation failed (missing fields, type mismatch,
            invalid URL, etc.).

    Design: DC-0001, DC-0003, DC-0004, DC-0005, ADR-0004
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

    try:
        cfg = Config.model_validate(raw)
    except ValidationError as exc:
        logger.error("Config validation failed: %s", exc)
        raise ValueError(f"Config validation failed: {exc}") from exc

    _config_instance = cfg
    return cfg


def get_config() -> Config:
    """Get the loaded global config instance.

    Returns:
        Config singleton.

    Raises:
        RuntimeError: Called before load_config().

    Design: DC-0005
    """
    if _config_instance is None:
        raise RuntimeError(
            "Config not loaded. Call load_config() before get_config()."
        )
    return _config_instance
