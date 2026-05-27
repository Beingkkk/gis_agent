"""Tests for core.workspace module.

Design: DC-0010, DC-0011, DC-0012, DC-0013, DC-0014
"""

from pathlib import Path
from unittest.mock import patch

import pytest

import core.workspace as _workspace_module
from core.workspace import (
    AgentsMdContent,
    PathNotFoundError,
    Workspace,
    WorkspaceError,
    WorkspaceNotFoundError,
    get_workspace,
    initialize,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_singleton() -> None:
    """Reset the global workspace singleton after each test."""
    _workspace_module._workspace_instance = None
    yield
    _workspace_module._workspace_instance = None


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    """Create a Workspace instance using a temporary directory."""
    return Workspace(tmp_path)


# ---------------------------------------------------------------------------
# W-01~W-02: Red phase — failing test skeletons
# ---------------------------------------------------------------------------


def test_workspace_init_with_valid_path(tmp_path: Path) -> None:
    """Normal initialization with an existing directory."""
    ws = Workspace(tmp_path)
    assert ws.root == tmp_path.resolve()


def test_workspace_init_with_relative_path(tmp_path: Path) -> None:
    """Initialization with a relative path resolves to absolute."""
    rel = Path(".") / tmp_path.name
    with patch.object(Path, "resolve", return_value=tmp_path.resolve()):
        ws = Workspace(rel)
        assert ws.root.is_absolute()


def test_workspace_init_nonexistent_dir() -> None:
    """Nonexistent directory raises WorkspaceNotFoundError."""
    with pytest.raises(WorkspaceNotFoundError):
        Workspace(Path("/nonexistent/path/for/workspace"))


def test_workspace_init_file_as_path(tmp_path: Path) -> None:
    """Using a file (not directory) as path raises WorkspaceNotFoundError."""
    file_path = tmp_path / "not_a_dir.txt"
    file_path.write_text("hello")
    with pytest.raises(WorkspaceNotFoundError):
        Workspace(file_path)


def test_root_property_returns_absolute_path(workspace: Workspace) -> None:
    """root property returns a Path that is absolute."""
    assert isinstance(workspace.root, Path)
    assert workspace.root.is_absolute()


def test_resolve_path_relative(workspace: Workspace) -> None:
    """Relative path is resolved against workspace root."""
    result = workspace.resolve_path("data/roads.shp")
    expected = workspace.root / "data" / "roads.shp"
    assert result == expected.resolve()


def test_resolve_path_absolute(workspace: Workspace, tmp_path: Path) -> None:
    """Absolute path is passed through directly (not restricted)."""
    # Use tmp_path (guaranteed absolute, outside workspace root)
    abs_path = tmp_path / "external" / "data.tif"
    result = workspace.resolve_path(str(abs_path))
    assert result == abs_path.resolve()


def test_resolve_path_must_exist_when_exists(workspace: Workspace) -> None:
    """must_exist=True with existing file succeeds."""
    file_path = workspace.root / "existing.shp"
    file_path.write_text("dummy")
    result = workspace.resolve_path("existing.shp", must_exist=True)
    assert result == file_path.resolve()


def test_resolve_path_must_exist_when_missing(workspace: Workspace) -> None:
    """must_exist=True with missing file raises PathNotFoundError."""
    with pytest.raises(PathNotFoundError):
        workspace.resolve_path("missing.shp", must_exist=True)


def test_generate_output_path_with_timestamp(workspace: Workspace) -> None:
    """Default generates path with timestamp appended."""
    result = workspace.generate_output_path("roads", ".geojson")
    assert result.parent == workspace.root
    name = result.name
    assert name.startswith("roads_")
    assert name.endswith(".geojson")
    # Timestamp format: roads_YYYYMMDD_HHMMSS.geojson
    assert len(name) > len("roads.geojson")


def test_generate_output_path_without_timestamp(workspace: Workspace) -> None:
    """timestamp=False generates path without timestamp."""
    result = workspace.generate_output_path("roads", ".geojson", timestamp=False)
    assert result.name == "roads.geojson"


def test_generate_output_path_absolute_base(
    workspace: Workspace, tmp_path: Path
) -> None:
    """Absolute user_input uses that as base directory."""
    abs_input = str(tmp_path / "output" / "result")
    result = workspace.generate_output_path(abs_input, ".sh")
    assert result.parent == (tmp_path / "output").resolve()


def test_generate_output_path_preserves_subdir(workspace: Workspace) -> None:
    """Subdirectory structure is preserved."""
    result = workspace.generate_output_path("processed/final", ".json")
    assert result.parent.name == "processed"
    assert result.name.startswith("final_")
    assert result.name.endswith(".json")


def test_load_agents_md_exists(workspace: Workspace) -> None:
    """Agents.md exists -> returns AgentsMdContent with full text."""
    agents_path = workspace.root / "Agents.md"
    agents_path.write_text("# Project Config\n- epsg: 4326\n", encoding="utf-8")
    result = workspace.load_agents_md()
    assert result is not None
    assert isinstance(result, AgentsMdContent)
    assert result.content == "# Project Config\n- epsg: 4326\n"
    assert result.path == agents_path


def test_load_agents_md_not_exists(workspace: Workspace) -> None:
    """Agents.md absent -> returns None."""
    result = workspace.load_agents_md()
    assert result is None


def test_load_agents_md_permission_error(workspace: Workspace) -> None:
    """Agents.md exists but unreadable -> raises WorkspaceError."""
    agents_path = workspace.root / "Agents.md"
    agents_path.write_text("content")
    with patch.object(
        Path,
        "read_text",
        side_effect=PermissionError("Permission denied"),
    ):
        with pytest.raises(WorkspaceError):
            workspace.load_agents_md()


def test_get_cwd_returns_root(workspace: Workspace) -> None:
    """get_cwd returns the workspace root."""
    assert workspace.get_cwd() == workspace.root


def test_initialize_creates_singleton(tmp_path: Path) -> None:
    """initialize creates a singleton accessible via get_workspace."""
    ws = initialize(tmp_path)
    assert ws is get_workspace()
    assert ws.root == tmp_path.resolve()


def test_get_workspace_before_initialize() -> None:
    """get_workspace before initialize raises RuntimeError."""
    with pytest.raises(RuntimeError):
        get_workspace()


def test_workspace_instance_is_immutable(workspace: Workspace) -> None:
    """Workspace attributes are read-only (no setters)."""
    with pytest.raises((AttributeError, TypeError)):
        workspace.root = Path("/tmp")  # type: ignore[misc]
