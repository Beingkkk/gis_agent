"""GIS Agent core module.

Submodules:
    workspace: Workspace management, path normalization, Agents.md loading
    models: TemplateDef, ParamDef, SessionState, Session data models

Public API:
    Workspace, AgentsMdContent
    WorkspaceError, WorkspaceNotFoundError, PathNotFoundError
    initialize(root), get_workspace()
    TemplateDef, ParamDef, SessionState, Session

Design: plan-workspace v2.0.0, plan-core v1.0.0
"""

from core.models import ParamDef, Session, SessionState, TemplateDef
from core.processor import SessionProcessor
from core.registry import TemplateRegistry
from core.validator import ParamValidator, ValidationResult
from core.workspace import (
    AgentsMdContent,
    PathNotFoundError,
    Workspace,
    WorkspaceError,
    WorkspaceNotFoundError,
    get_workspace,
    initialize,
)

__all__ = [
    "AgentsMdContent",
    "ParamDef",
    "ParamValidator",
    "PathNotFoundError",
    "Session",
    "SessionProcessor",
    "SessionState",
    "TemplateDef",
    "TemplateRegistry",
    "ValidationResult",
    "Workspace",
    "WorkspaceError",
    "WorkspaceNotFoundError",
    "get_workspace",
    "initialize",
]
