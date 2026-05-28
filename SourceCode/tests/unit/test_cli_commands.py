"""Tests for SlashCommandHandler.

Design: plan-cli v1.0.0 (DC-0062)
"""

from pathlib import Path

import pytest

from cli.commands import SlashCommandHandler
from core.models import Session, SessionState, TemplateDef
from core.registry import TemplateRegistry
from core.workspace import Workspace


@pytest.fixture
def handler() -> SlashCommandHandler:
    """SlashCommandHandler fixture."""
    return SlashCommandHandler()


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    """Temporary workspace fixture."""
    return Workspace(tmp_path)


@pytest.fixture
def registry() -> TemplateRegistry:
    """TemplateRegistry fixture with sample templates."""
    templates = [
        TemplateDef(
            id="shp2geojson",
            name="Shapefile 转 GeoJSON",
            description="将 Shapefile 转换为 GeoJSON",
            template_file="vector/shp2geojson.j2",
        ),
        TemplateDef(
            id="clip_raster",
            name="栅格裁剪",
            description="使用边界裁剪栅格",
            template_file="raster/clip_raster.j2",
        ),
    ]
    return TemplateRegistry(templates, template_dir=Path("/templates"))


@pytest.fixture
def session() -> Session:
    """Session fixture in IDLE state."""
    return Session()


class TestQuitCommand:
    """/quit and /q commands."""

    def test_quit_returns_quit_action(
        self,
        handler: SlashCommandHandler,
        session: Session,
        registry: TemplateRegistry,
        workspace: Workspace,
    ) -> None:
        """/quit returns QUIT action."""
        new_session, response, action = handler.handle(
            "/quit", session, registry, workspace
        )
        assert action == "QUIT"
        assert "再见" in response or "quit" in response.lower()

    def test_quit_alias_q(
        self,
        handler: SlashCommandHandler,
        session: Session,
        registry: TemplateRegistry,
        workspace: Workspace,
    ) -> None:
        """/q is alias for /quit."""
        _, _, action = handler.handle("/q", session, registry, workspace)
        assert action == "QUIT"


class TestClearCommand:
    """/clear command."""

    def test_clear_resets_session(
        self,
        handler: SlashCommandHandler,
        registry: TemplateRegistry,
        workspace: Workspace,
    ) -> None:
        """/clear resets session to IDLE with empty state."""
        session = Session(
            state=SessionState.PARAM_COLLECT,
            history=[],
            template=registry.get_template("shp2geojson"),
            params={"input": "test.shp"},
        )
        new_session, response, action = handler.handle(
            "/clear", session, registry, workspace
        )
        assert action is None
        assert new_session.state == SessionState.IDLE
        assert new_session.template is None
        assert new_session.params == {}
        assert new_session.history == []


class TestWorkspaceCommand:
    """/workspace command."""

    def test_workspace_shows_path(
        self,
        handler: SlashCommandHandler,
        session: Session,
        registry: TemplateRegistry,
        workspace: Workspace,
    ) -> None:
        """/workspace shows current workspace root path."""
        new_session, response, action = handler.handle(
            "/workspace", session, registry, workspace
        )
        assert action is None
        assert str(workspace.root) in response


class TestTemplatesCommand:
    """/templates command."""

    def test_templates_lists_all(
        self,
        handler: SlashCommandHandler,
        session: Session,
        registry: TemplateRegistry,
        workspace: Workspace,
    ) -> None:
        """/templates lists all available templates."""
        new_session, response, action = handler.handle(
            "/templates", session, registry, workspace
        )
        assert action is None
        assert "shp2geojson" in response
        assert "clip_raster" in response
        assert "Shapefile 转 GeoJSON" in response
        assert "栅格裁剪" in response


class TestStatusCommand:
    """/status command."""

    def test_status_shows_idle(
        self,
        handler: SlashCommandHandler,
        session: Session,
        registry: TemplateRegistry,
        workspace: Workspace,
    ) -> None:
        """/status shows IDLE state info."""
        new_session, response, action = handler.handle(
            "/status", session, registry, workspace
        )
        assert action is None
        assert "IDLE" in response
        assert str(workspace.root) in response
        assert "0" in response  # history count

    def test_status_shows_param_collect(
        self,
        handler: SlashCommandHandler,
        registry: TemplateRegistry,
        workspace: Workspace,
    ) -> None:
        """/status shows PARAM_COLLECT state with template."""
        session = Session(
            state=SessionState.PARAM_COLLECT,
            template=registry.get_template("shp2geojson"),
            history=[],
        )
        _, response, _ = handler.handle("/status", session, registry, workspace)
        assert "PARAM_COLLECT" in response
        assert "shp2geojson" in response


class TestHelpCommand:
    """/help command."""

    def test_help_shows_commands(
        self,
        handler: SlashCommandHandler,
        session: Session,
        registry: TemplateRegistry,
        workspace: Workspace,
    ) -> None:
        """/help lists available slash commands."""
        new_session, response, action = handler.handle(
            "/help", session, registry, workspace
        )
        assert action is None
        assert "/quit" in response
        assert "/clear" in response
        assert "/workspace" in response
        assert "/templates" in response
        assert "/status" in response
        assert "/help" in response


class TestUnknownCommand:
    """Unknown slash commands."""

    def test_unknown_shows_help_hint(
        self,
        handler: SlashCommandHandler,
        session: Session,
        registry: TemplateRegistry,
        workspace: Workspace,
    ) -> None:
        """Unknown command shows friendly error and /help hint."""
        new_session, response, action = handler.handle(
            "/foo", session, registry, workspace
        )
        assert action is None
        assert (
            "未知" in response or "Unknown" in response or "unknown" in response.lower()
        )
        assert "/help" in response

    def test_command_with_args_ignored(
        self,
        handler: SlashCommandHandler,
        session: Session,
        registry: TemplateRegistry,
        workspace: Workspace,
    ) -> None:
        """Extra arguments after command are ignored."""
        _, response, action = handler.handle("/quit now", session, registry, workspace)
        assert action == "QUIT"
