"""Workspace management module.

Provides project anchor point, path normalization,
and default cwd for script execution.

Public API:
    initialize(root) -> Workspace
    get_workspace() -> Workspace
    Workspace.resolve_path(user_input) -> Path
    Workspace.generate_output_path(user_input, ext) -> Path

Design: plan-workspace v2.0.0 (DC-0010 ~ DC-0014)
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


class WorkspaceError(Exception):
    """Base exception for workspace module."""


class WorkspaceNotFoundError(WorkspaceError):
    """Workspace directory does not exist or is not a directory."""


class PathNotFoundError(WorkspaceError):
    """File path does not exist (informational check, not security block)."""


class Workspace:
    """Workspace manager.

    Provides path normalization, output filename generation.
    Process-level singleton, accessed via initialize() / get_workspace().

    Design:
        DC-0010, DC-0011, DC-0012, DC-0014
    """

    def __init__(self, root: Path) -> None:
        """Initialize workspace.

        Args:
            root: Workspace root directory path. Resolved to absolute path.

        Raises:
            WorkspaceNotFoundError: Directory does not exist or is not a dir.
        """
        resolved = root.resolve()
        if not resolved.exists() or not resolved.is_dir():
            raise WorkspaceNotFoundError(
                f"Workspace not found or not a directory: {resolved}"
            )
        self._root = resolved

    @property
    def root(self) -> Path:
        """Return workspace root directory (absolute path)."""
        return self._root

    def resolve_path(self, user_input: str, must_exist: bool = False) -> Path:
        """Resolve user input path to normalized absolute path.

        Relative paths are resolved against workspace.root.
        Absolute paths are passed through directly.
        No scope restriction -- workspace is not a security boundary.

        Args:
            user_input: User-provided path (relative or absolute).
            must_exist: Whether to check if the path exists.

        Returns:
            Normalized absolute Path.

        Raises:
            PathNotFoundError: must_exist=True and path does not exist.
        """
        path = Path(user_input)
        if path.is_absolute():
            resolved = path.resolve()
        else:
            resolved = (self._root / path).resolve()

        if must_exist and not resolved.exists():
            raise PathNotFoundError(f"Path does not exist: {resolved}")

        return resolved

    def generate_output_path(
        self,
        user_input: str,
        ext: str,
        timestamp: bool = True,
    ) -> Path:
        """Generate output file path with optional timestamp.

        Args:
            user_input: Base filename (may contain subdirs, no ext).
            ext: File extension (e.g. ".json", ".bat").
            timestamp: Whether to append timestamp. Default True.

        Returns:
            Normalized absolute output path.
        """
        path = Path(user_input)

        if path.is_absolute():
            parent = path.parent
            stem = path.name
        else:
            parent = self._root / path.parent
            stem = path.name

        if timestamp:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{stem}_{ts}{ext}"
        else:
            filename = f"{stem}{ext}"

        return (parent / filename).resolve()

    def get_cwd(self) -> Path:
        """Return workspace root as default cwd for script execution."""
        return self._root


_workspace_instance: Optional[Workspace] = None


def initialize(root: Path) -> Workspace:
    """Initialize global workspace singleton.

    Args:
        root: Workspace root directory.

    Returns:
        Workspace instance.
    """
    global _workspace_instance
    _workspace_instance = Workspace(root)
    return _workspace_instance


def get_workspace() -> Workspace:
    """Get initialized workspace singleton.

    Returns:
        Workspace instance.

    Raises:
        RuntimeError: Called before initialize().
    """
    if _workspace_instance is None:
        raise RuntimeError("Workspace not initialized. Call initialize() first.")
    return _workspace_instance


def change_workspace(root: Path) -> Workspace:
    """Change the global workspace singleton to a new root.

    Re-initializes the workspace with the new path. Old references
    to the previous workspace will be stale.

    Args:
        root: New workspace root directory.

    Returns:
        New Workspace instance.

    Raises:
        WorkspaceNotFoundError: Directory does not exist or is not a dir.
    """
    global _workspace_instance
    _workspace_instance = Workspace(root)
    return _workspace_instance


def _reset_singleton() -> None:
    """Reset the global singleton. For testing only."""
    global _workspace_instance
    _workspace_instance = None
