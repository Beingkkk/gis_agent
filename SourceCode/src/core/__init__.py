"""GIS Agent core module.

Submodules:
    workspace: Workspace management, path normalization, Agents.md loading

Public API:
    Workspace, AgentsMdContent
    WorkspaceError, WorkspaceNotFoundError, PathNotFoundError
    initialize(root), get_workspace()

Design: plan-workspace v2.0.0, plan-core v1.0.0
"""

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
    "PathNotFoundError",
    "Workspace",
    "WorkspaceError",
    "WorkspaceNotFoundError",
    "get_workspace",
    "initialize",
]
