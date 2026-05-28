"""REPL interactive loop for GIS Agent.

Provides the main user interaction loop: input reading, slash command
dispatch, state machine integration, and script execution confirmation.

Design: plan-cli v1.0.0 (DC-0061, DC-0062, DC-0066)
"""

import logging
from typing import Callable, Optional

from cli.commands import SlashCommandHandler
from cli.executor import ScriptExecutor
from core.models import Session, SessionState
from core.processor import SessionProcessor
from core.registry import TemplateRegistry
from core.workspace import Workspace
from templates.engine import RenderedScript

logger = logging.getLogger(__name__)


class REPL:
    """Read-Eval-Print Loop for GIS Agent.

    Manages user input reading, slash command dispatch, state machine
    invocation, and response output.

    Design:
        DC-0061, DC-0062, DC-0066
    """

    def __init__(
        self,
        processor: SessionProcessor,
        executor: ScriptExecutor,
        slash_handler: SlashCommandHandler,
        registry: TemplateRegistry,
        workspace: Workspace,
        dry_run: bool = False,
        input_fn: Optional[Callable[[str], str]] = None,
        output_fn: Optional[Callable[[str], None]] = None,
        render_fn: Optional[Callable[[Session], RenderedScript]] = None,
    ) -> None:
        """Initialize REPL with dependencies.

        Args:
            processor: Session state machine processor.
            executor: Script executor for SCRIPT_PREVIEW state.
            slash_handler: Slash command dispatcher.
            registry: Template registry for slash commands.
            workspace: Current workspace for slash commands.
            dry_run: If True, preview scripts instead of executing.
            input_fn: Input function (default: builtin input).
            output_fn: Output function (default: builtin print).
            render_fn: Optional callback to render a script from session.
                If None, SCRIPT_PREVIEW execution is skipped (test mode).
        """
        self._processor = processor
        self._executor = executor
        self._slash_handler = slash_handler
        self._registry = registry
        self._workspace = workspace
        self._dry_run = dry_run
        self._input_fn = input_fn if input_fn is not None else input
        self._output_fn = output_fn if output_fn is not None else print
        self._render_fn = render_fn

    def run(self, session: Session) -> None:
        """Start the REPL loop.

        Args:
            session: Initial session state.
        """
        while True:
            try:
                user_input = self._read_input()
            except EOFError:
                self._output_fn("再见。")
                break
            except KeyboardInterrupt:
                self._output_fn("^C，使用 /quit 退出")
                continue

            if user_input.startswith("/"):
                session, response, action = self._slash_handler.handle(
                    user_input, session, self._registry, self._workspace
                )
                if action == "QUIT":
                    self._output_fn(response)
                    break
                self._output_fn(response)
                continue

            session, response = self._processor.process(session, user_input)
            self._output_fn(response)

            if session.state == SessionState.SCRIPT_PREVIEW:
                session = self._handle_execution(session)

    def _read_input(self) -> str:
        """Read user input with prompt.

        Returns:
            User input string.
        """
        return self._input_fn("GIS> ")

    def _handle_execution(self, session: Session) -> Session:
        """Handle SCRIPT_PREVIEW state: Y/N confirmation and execution.

        Args:
            session: Current session in SCRIPT_PREVIEW state.

        Returns:
            Updated session (IDLE or PARAM_COLLECT).
        """
        if self._dry_run:
            if self._render_fn is not None:
                script = self._render_fn(session)
                self._executor.preview(script)
            self._output_fn("dry-run 模式，跳过执行。")
            return session.with_state(SessionState.IDLE)

        if self._render_fn is None:
            self._output_fn("警告：未配置脚本渲染，跳过执行。")
            return session.with_state(SessionState.IDLE)

        while True:
            confirm = self._input_fn("确认执行？(Y/N)：").strip().upper()
            if confirm == "Y":
                return self._execute_script(session)
            elif confirm == "N":
                self._output_fn("已取消。请修改参数。")
                return session.with_state(SessionState.PARAM_COLLECT)
            else:
                self._output_fn("请输入 Y 确认执行，或 N 取消。")

    def _execute_script(self, session: Session) -> Session:
        """Execute the script and return to IDLE.

        Args:
            session: Session containing the script to execute.

        Returns:
            Session in IDLE state.
        """
        if self._render_fn is None:
            self._output_fn("警告：未配置脚本渲染，跳过执行。")
            return session.with_state(SessionState.IDLE)

        script = self._render_fn(session)
        self._output_fn("开始执行...")
        result = self._executor.execute(script)
        if result.success:
            self._output_fn(result.stdout if result.stdout else "执行完成。")
        else:
            self._output_fn(f"执行失败：{result.stderr}")
        return session.with_state(SessionState.IDLE)
