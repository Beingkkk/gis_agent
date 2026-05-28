"""Tests for REPL interactive loop.

Design: plan-cli v1.0.0 (DC-0061, DC-0062, DC-0066)
"""

from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

import pytest

from cli.commands import SlashCommandHandler
from cli.executor import ExecutionResult, ScriptExecutor
from cli.repl import REPL
from core.models import Session, SessionState
from core.processor import SessionProcessor
from core.registry import TemplateRegistry
from core.workspace import Workspace
from templates.engine import Platform, RenderedScript


@pytest.fixture
def mock_processor() -> MagicMock:
    """Mock SessionProcessor."""
    return MagicMock(spec=SessionProcessor)


@pytest.fixture
def mock_executor() -> MagicMock:
    """Mock ScriptExecutor."""
    return MagicMock(spec=ScriptExecutor)


@pytest.fixture
def mock_registry() -> MagicMock:
    """Mock TemplateRegistry."""
    registry = MagicMock(spec=TemplateRegistry)
    registry.list_templates.return_value = []
    return registry


@pytest.fixture
def mock_workspace(tmp_path: Path) -> MagicMock:
    """Mock Workspace."""
    ws = MagicMock(spec=Workspace)
    ws.root = tmp_path
    return ws


@pytest.fixture
def slash_handler() -> SlashCommandHandler:
    """Real SlashCommandHandler (lightweight, no external deps)."""
    return SlashCommandHandler()


@pytest.fixture
def mock_rendered_script() -> RenderedScript:
    """Sample RenderedScript for tests."""
    return RenderedScript(
        content="@echo off\necho hello\n",
        command_lines=["echo hello"],
        platform=Platform.WINDOWS,
        output_path="test.bat",
    )


def make_repl(
    processor: MagicMock,
    executor: MagicMock,
    slash_handler: SlashCommandHandler,
    registry: MagicMock,
    workspace: MagicMock,
    inputs: list[str],
    dry_run: bool = False,
    render_fn: Optional[MagicMock] = None,
) -> tuple[REPL, list[str]]:
    """Create a REPL with controlled input and captured output.

    Returns:
        (repl_instance, captured_outputs)
    """
    input_iter = iter(inputs)
    outputs: list[str] = []

    def input_fn(prompt: str = "") -> str:
        return next(input_iter)

    def output_fn(text: str) -> None:
        outputs.append(text)

    repl = REPL(
        processor=processor,
        executor=executor,
        slash_handler=slash_handler,
        registry=registry,
        workspace=workspace,
        dry_run=dry_run,
        input_fn=input_fn,
        output_fn=output_fn,
        render_fn=render_fn,
    )
    return repl, outputs


class TestREPLBasicLoop:
    """Basic REPL loop behaviour."""

    def test_normal_input_passed_to_processor(
        self,
        mock_processor: MagicMock,
        mock_executor: MagicMock,
        slash_handler: SlashCommandHandler,
        mock_registry: MagicMock,
        mock_workspace: MagicMock,
    ) -> None:
        """Normal input is passed to SessionProcessor.process()."""
        mock_processor.process.return_value = (
            Session(state=SessionState.IDLE),
            "ok",
        )
        repl, outputs = make_repl(
            mock_processor,
            mock_executor,
            slash_handler,
            mock_registry,
            mock_workspace,
            inputs=["hello", "/quit"],
        )
        repl.run(Session())

        mock_processor.process.assert_called_once()
        call_args = mock_processor.process.call_args[0]
        assert call_args[1] == "hello"

    def test_repl_prints_response(
        self,
        mock_processor: MagicMock,
        mock_executor: MagicMock,
        slash_handler: SlashCommandHandler,
        mock_registry: MagicMock,
        mock_workspace: MagicMock,
    ) -> None:
        """Processor response is printed."""
        mock_processor.process.return_value = (
            Session(state=SessionState.IDLE),
            "系统响应",
        )
        repl, outputs = make_repl(
            mock_processor,
            mock_executor,
            slash_handler,
            mock_registry,
            mock_workspace,
            inputs=["hello", "/quit"],
        )
        repl.run(Session())

        assert "系统响应" in outputs


class TestREPLSlashCommands:
    """Slash command routing in REPL."""

    def test_quit_terminates_loop(
        self,
        mock_processor: MagicMock,
        mock_executor: MagicMock,
        slash_handler: SlashCommandHandler,
        mock_registry: MagicMock,
        mock_workspace: MagicMock,
    ) -> None:
        """/quit terminates the REPL loop."""
        repl, outputs = make_repl(
            mock_processor,
            mock_executor,
            slash_handler,
            mock_registry,
            mock_workspace,
            inputs=["/quit"],
        )
        repl.run(Session())

        # Should not call processor for slash commands
        mock_processor.process.assert_not_called()
        assert any("再见" in o for o in outputs)

    def test_clear_resets_session(
        self,
        mock_processor: MagicMock,
        mock_executor: MagicMock,
        slash_handler: SlashCommandHandler,
        mock_registry: MagicMock,
        mock_workspace: MagicMock,
    ) -> None:
        """/clear resets session and continues loop."""
        mock_processor.process.return_value = (
            Session(state=SessionState.IDLE),
            "ok",
        )
        repl, outputs = make_repl(
            mock_processor,
            mock_executor,
            slash_handler,
            mock_registry,
            mock_workspace,
            inputs=["/clear", "hello", "/quit"],
        )
        repl.run(Session())

        # After /clear, subsequent "hello" should be processed with a fresh session
        assert mock_processor.process.call_count == 1
        # The session passed to process should be IDLE (reset by /clear)
        passed_session = mock_processor.process.call_args[0][0]
        assert passed_session.state == SessionState.IDLE
        assert passed_session.history == []


class TestREPLScriptPreview:
    """SCRIPT_PREVIEW state — Y/N confirmation."""

    def test_y_confirms_execution(
        self,
        mock_processor: MagicMock,
        mock_executor: MagicMock,
        slash_handler: SlashCommandHandler,
        mock_registry: MagicMock,
        mock_workspace: MagicMock,
        mock_rendered_script: RenderedScript,
    ) -> None:
        """Y confirms and executes script, returns to IDLE."""
        mock_render_fn = MagicMock(return_value=mock_rendered_script)
        mock_processor.process.side_effect = [
            (Session(state=SessionState.SCRIPT_PREVIEW), "脚本...\n确认执行？(Y/N)："),
            (Session(state=SessionState.IDLE), "完成"),
        ]
        mock_executor.execute.return_value = ExecutionResult(
            success=True, returncode=0, stdout="done", stderr="", duration_ms=100
        )
        repl, outputs = make_repl(
            mock_processor,
            mock_executor,
            slash_handler,
            mock_registry,
            mock_workspace,
            inputs=["run it", "Y", "/quit"],
            render_fn=mock_render_fn,
        )
        repl.run(Session())

        mock_executor.execute.assert_called_once()
        assert any("done" in o for o in outputs)

    def test_n_cancels_returns_collect(
        self,
        mock_processor: MagicMock,
        mock_executor: MagicMock,
        slash_handler: SlashCommandHandler,
        mock_registry: MagicMock,
        mock_workspace: MagicMock,
        mock_rendered_script: RenderedScript,
    ) -> None:
        """N cancels and returns to PARAM_COLLECT."""
        mock_render_fn = MagicMock(return_value=mock_rendered_script)
        mock_processor.process.side_effect = [
            (Session(state=SessionState.SCRIPT_PREVIEW), "脚本...\n确认执行？(Y/N)："),
            (Session(state=SessionState.IDLE), "好的"),
        ]
        repl, outputs = make_repl(
            mock_processor,
            mock_executor,
            slash_handler,
            mock_registry,
            mock_workspace,
            inputs=["run it", "N", "修改参数", "/quit"],
            render_fn=mock_render_fn,
        )
        repl.run(Session())

        mock_executor.execute.assert_not_called()
        # After N, the next natural language input goes to processor with
        # PARAM_COLLECT state
        second_call_session = mock_processor.process.call_args_list[1][0][0]
        assert second_call_session.state == SessionState.PARAM_COLLECT

    def test_invalid_confirmation_loops(
        self,
        mock_processor: MagicMock,
        mock_executor: MagicMock,
        slash_handler: SlashCommandHandler,
        mock_registry: MagicMock,
        mock_workspace: MagicMock,
        mock_rendered_script: RenderedScript,
    ) -> None:
        """Invalid input loops until Y/N is given."""
        mock_render_fn = MagicMock(return_value=mock_rendered_script)
        mock_processor.process.side_effect = [
            (Session(state=SessionState.SCRIPT_PREVIEW), "脚本...\n确认执行？(Y/N)："),
            (Session(state=SessionState.IDLE), "完成"),
        ]
        mock_executor.execute.return_value = ExecutionResult(
            success=True, returncode=0, stdout="", stderr="", duration_ms=0
        )
        repl, outputs = make_repl(
            mock_processor,
            mock_executor,
            slash_handler,
            mock_registry,
            mock_workspace,
            inputs=["run it", "foo", "", "Y", "/quit"],
            render_fn=mock_render_fn,
        )
        repl.run(Session())

        mock_executor.execute.assert_called_once()
        # Should have prompted for retry
        assert any("Y" in o and "N" in o for o in outputs)

    def test_execution_failure_shows_stderr(
        self,
        mock_processor: MagicMock,
        mock_executor: MagicMock,
        slash_handler: SlashCommandHandler,
        mock_registry: MagicMock,
        mock_workspace: MagicMock,
        mock_rendered_script: RenderedScript,
    ) -> None:
        """Execution failure prints stderr and returns to IDLE."""
        mock_render_fn = MagicMock(return_value=mock_rendered_script)
        mock_processor.process.side_effect = [
            (Session(state=SessionState.SCRIPT_PREVIEW), "脚本..."),
            (Session(state=SessionState.IDLE), "继续"),
        ]
        mock_executor.execute.return_value = ExecutionResult(
            success=False, returncode=1, stdout="", stderr="GDAL error", duration_ms=50
        )
        repl, outputs = make_repl(
            mock_processor,
            mock_executor,
            slash_handler,
            mock_registry,
            mock_workspace,
            inputs=["run it", "Y", "/quit"],
            render_fn=mock_render_fn,
        )
        repl.run(Session())

        assert any("GDAL error" in o for o in outputs)


class TestREPLDryRun:
    """Dry-run mode."""

    def test_dry_run_skips_execution(
        self,
        mock_processor: MagicMock,
        mock_executor: MagicMock,
        slash_handler: SlashCommandHandler,
        mock_registry: MagicMock,
        mock_workspace: MagicMock,
        mock_rendered_script: RenderedScript,
    ) -> None:
        """dry_run=True calls preview() not execute(), skips to IDLE."""
        mock_render_fn = MagicMock(return_value=mock_rendered_script)
        mock_processor.process.return_value = (
            Session(state=SessionState.SCRIPT_PREVIEW),
            "脚本内容",
        )
        repl, outputs = make_repl(
            mock_processor,
            mock_executor,
            slash_handler,
            mock_registry,
            mock_workspace,
            inputs=["run it", "/quit"],
            dry_run=True,
            render_fn=mock_render_fn,
        )
        repl.run(Session())

        mock_executor.preview.assert_called_once()
        mock_executor.execute.assert_not_called()
        assert any("dry-run" in o or "跳过" in o for o in outputs)


class TestREPLInterrupts:
    """Keyboard and EOF handling."""

    def test_ctrl_c_shows_hint(
        self,
        mock_processor: MagicMock,
        mock_executor: MagicMock,
        slash_handler: SlashCommandHandler,
        mock_registry: MagicMock,
        mock_workspace: MagicMock,
    ) -> None:
        """Ctrl+C shows hint and continues loop."""
        call_count = 0

        def failing_then_ok(*args: object, **kwargs: object) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise KeyboardInterrupt
            return "/quit"

        repl, outputs = make_repl(
            mock_processor,
            mock_executor,
            slash_handler,
            mock_registry,
            mock_workspace,
            inputs=[],  # not used
        )
        # Replace input_fn with our custom one
        repl._input_fn = failing_then_ok
        repl.run(Session())

        assert any("/quit" in o for o in outputs)
        mock_processor.process.assert_not_called()  # interrupted before processing

    def test_ctrl_d_exits(
        self,
        mock_processor: MagicMock,
        mock_executor: MagicMock,
        slash_handler: SlashCommandHandler,
        mock_registry: MagicMock,
        mock_workspace: MagicMock,
    ) -> None:
        """Ctrl+D (EOFError) exits gracefully."""

        def raise_eof(*args: object, **kwargs: object) -> str:
            raise EOFError

        repl, outputs = make_repl(
            mock_processor,
            mock_executor,
            slash_handler,
            mock_registry,
            mock_workspace,
            inputs=[],
        )
        repl._input_fn = raise_eof
        repl.run(Session())

        assert any("再见" in o for o in outputs)
        mock_processor.process.assert_not_called()
