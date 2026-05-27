"""Core data models for GIS Agent.

Provides TemplateDef and ParamDef dataclasses used by both core/
and templates/ modules.

Public API:
    ParamDef — parameter definition
    TemplateDef — template definition

Design: plan-core v1.0.0 (DC-0041)
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class ParamDef:
    """Parameter definition (from template registry).

    Design:
        DC-0041
    """

    name: str
    type: str
    required: bool
    description: str
    default: Optional[str] = None


@dataclass(frozen=True)
class TemplateDef:
    """Template definition (from template registry).

    Design:
        DC-0041
    """

    id: str
    name: str
    description: str
    template_file: str
    params: List[ParamDef] = field(default_factory=list)
