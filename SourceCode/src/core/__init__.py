"""GIS Agent core module.

Submodules:
    workspace: Workspace management, path normalization, Agents.md loading
    models: TemplateDef and ParamDef data models

Public API:
    Workspace, AgentsMdContent
    WorkspaceError, WorkspaceNotFoundError, PathNotFoundError
    initialize(root), get_workspace()
    TemplateDef, ParamDef

Design: plan-workspace v2.0.0, plan-core v1.0.0
"""

from core.models import ParamDef, TemplateDef
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
    "PathNotFoundError",
    "TemplateDef",
    "Workspace",
    "WorkspaceError",
    "WorkspaceNotFoundError",
    "get_workspace",
    "initialize",
]
