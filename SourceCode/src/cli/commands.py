"""Slash command handler for GIS Agent REPL.

Provides system-level commands accessible via / prefix.

Design: plan-cli v1.0.0 (DC-0062)
"""

from typing import Callable, Optional

from core.models import Session
from core.registry import TemplateRegistry
from core.workspace import Workspace


class SlashCommandHandler:
    """Handles slash commands in the REPL.

    Commands:
        /quit, /q     — Exit the application
        /clear        — Reset session to IDLE
        /workspace    — Show current workspace path
        /templates    — List available templates
        /status       — Show session status summary
        /help         — Show command list

    Design:
        DC-0062
    """

    def __init__(self) -> None:
        """Initialize command dispatch table."""
        self._commands: dict[str, Callable[..., tuple[Session, str, Optional[str]]]] = {
            "quit": self._cmd_quit,
            "q": self._cmd_quit,
            "clear": self._cmd_clear,
            "workspace": self._cmd_workspace,
            "templates": self._cmd_templates,
            "status": self._cmd_status,
            "help": self._cmd_help,
        }

    def handle(
        self,
        command_line: str,
        session: Session,
        registry: TemplateRegistry,
        workspace: Workspace,
    ) -> tuple[Session, str, Optional[str]]:
        """Process a slash command.

        Args:
            command_line: Full command line (e.g., "/quit" or "/templates").
            session: Current session state.
            registry: Template registry for /templates command.
            workspace: Current workspace for /workspace command.

        Returns:
            (new_session, response_text, action_flag)
            action_flag: None for normal response, "QUIT" to exit.
        """
        # Strip leading "/" and split to get command name (ignore extra args)
        parts = command_line.lstrip("/").strip().split()
        if not parts:
            return session, "请输入命令。输入 /help 查看可用命令。", None

        command = parts[0].lower()
        handler = self._commands.get(command)
        if handler is None:
            return (
                session,
                f"未知命令：/{command}。输入 /help 查看可用命令。",
                None,
            )

        return handler(session, registry, workspace)

    # ------------------------------------------------------------------
    # Individual command handlers
    # ------------------------------------------------------------------

    def _cmd_quit(
        self,
        session: Session,
        _registry: TemplateRegistry,
        _workspace: Workspace,
    ) -> tuple[Session, str, Optional[str]]:
        """Exit the application."""
        return session, "再见。", "QUIT"

    def _cmd_clear(
        self,
        session: Session,
        _registry: TemplateRegistry,
        _workspace: Workspace,
    ) -> tuple[Session, str, Optional[str]]:
        """Reset session to IDLE state."""
        return (
            Session(),  # fresh session
            "会话已清除。",
            None,
        )

    def _cmd_workspace(
        self,
        session: Session,
        _registry: TemplateRegistry,
        workspace: Workspace,
    ) -> tuple[Session, str, Optional[str]]:
        """Show current workspace path."""
        return session, f"当前工作空间：{workspace.root}", None

    def _cmd_templates(
        self,
        session: Session,
        registry: TemplateRegistry,
        _workspace: Workspace,
    ) -> tuple[Session, str, Optional[str]]:
        """List available templates."""
        templates = registry.list_templates()
        if not templates:
            return session, "没有可用的模板。", None

        lines = ["可用模板："]
        for t in templates:
            lines.append(f"  {t.id}: {t.name}")
        return session, "\n".join(lines), None

    def _cmd_status(
        self,
        session: Session,
        registry: TemplateRegistry,
        workspace: Workspace,
    ) -> tuple[Session, str, Optional[str]]:
        """Show session status summary."""
        template_id = session.template.id if session.template else "无"
        lines = [
            "状态摘要：",
            f"  当前状态：{session.state.name}",
            f"  工作空间：{workspace.root}",
            f"  对话轮数：{len(session.history)}",
            f"  当前模板：{template_id}",
            f"  可用模板数：{len(registry.list_templates())}",
        ]
        return session, "\n".join(lines), None

    def _cmd_help(
        self,
        session: Session,
        _registry: TemplateRegistry,
        _workspace: Workspace,
    ) -> tuple[Session, str, Optional[str]]:
        """Show help text."""
        lines = [
            "可用命令：",
            "  /quit, /q     — 退出程序",
            "  /clear        — 清除会话历史",
            "  /workspace    — 显示当前工作空间路径",
            "  /templates    — 列出可用模板",
            "  /status       — 显示当前状态",
            "  /help         — 显示此帮助信息",
        ]
        return session, "\n".join(lines), None
