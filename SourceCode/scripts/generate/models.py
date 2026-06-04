"""Data models for J2 template generation.

Design: plan-j2-generate DC-0082, DC-0088
"""

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Add src/ to path for shared llm.template_generator imports
_SRC_DIR = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(_SRC_DIR))

from llm.template_generator import _extract_template_vars


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

_VALID_PARAM_TYPES: frozenset[str] = frozenset(
    {
        "file_path",
        "folder_path",
        "crs",
        "string",
        "text",
        "boolean",
        "integer",
        "float",
        "enum",
        "format",
    }
)
_VALID_CATEGORIES: frozenset[str] = frozenset({"vector", "raster", "general"})

_ID_PATTERN: re.Pattern[str] = re.compile(r"^[a-z0-9_]+$")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParamDef:
    """Parameter definition within a template."""

    name: str
    type: str
    required: bool
    description: str
    default: str | None = None
    options: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.type not in _VALID_PARAM_TYPES:
            raise ValueError(f"Invalid param type: {self.type!r}")


@dataclass(frozen=True)
class TemplateDefinition:
    """Intermediate representation of a Jinja2 template.

    Design: DC-0082
    """

    id: str
    name: str
    description: str
    category: str
    command_template: str
    params: list[ParamDef]
    concepts: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    common_errors: list[dict[str, str]] = field(default_factory=list)
    seealso: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not _ID_PATTERN.match(self.id):
            raise ValueError(f"Invalid id format: {self.id!r}")
        if self.category not in _VALID_CATEGORIES:
            raise ValueError(f"Invalid category: {self.category!r}")

        param_names = {p.name for p in self.params}
        for p in self.params:
            if p.required and p.default is not None:
                raise ValueError(f"Required param {p.name!r} cannot have default")

        # Check that all template variables in command_template correspond to declared params
        all_vars = _extract_template_vars(self.command_template)
        undeclared = all_vars - param_names
        if undeclared:
            raise ValueError(f"Command template uses undeclared params: {undeclared}")


@dataclass(frozen=True)
class ExtractedDoc:
    """Generic document extraction result, input to LLM generator.

    Design: DC-0088
    """

    title: str
    synopsis: str
    description: str
    options: list[dict[str, Any]] = field(default_factory=list)
