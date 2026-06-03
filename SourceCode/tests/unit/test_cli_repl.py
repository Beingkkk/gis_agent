"""Tests for REPL interactive loop.

【已废弃，代码保留】CLI 层不再维护，参见 constitution.md §6.1。
Design: Document/archive/plan-cli.md (DC-0061, DC-0062, DC-0066)
"""

from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

import pytest

from cli.commands import SlashCommandHandler
from cli.executor import ExecutionResult, ScriptExecutor
from cli.repl import REPL
from core.models import Session, SessionState, TemplateDef
from llm.models import Message
from core.processor import SessionProcessor
from core.registry import TemplateRegistry
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
    ) -> None:
        """/quit terminates the REPL loop."""
        repl, outputs = make_repl(
            mock_processor,
            mock_executor,
            slash_handler,
            mock_registry,
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
        mock_rendered_script: RenderedScript,
    ) -> None:
        """N cancels and returns to PARAM_COLLECT."""
        mock_render_fn = MagicMock(return_value=mock_rendered_script)
        mock_processor.process.side_effect = [
            (
                Session(state=SessionState.SCRIPT_PREVIEW),
                "脚本...\n确认执行？(Y/N)：",
            ),
            (Session(state=SessionState.IDLE), "完成"),
        ]
        repl, outputs = make_repl(
            mock_processor,
            mock_executor,
            slash_handler,
            mock_registry,
            inputs=["run it", "N", "/quit"],
            render_fn=mock_render_fn,
        )
        repl.run(Session())

        mock_executor.execute.assert_not_called()
        assert any("取消" in o for o in outputs)

    def test_dry_run_previews_no_execute(
        self,
        mock_processor: MagicMock,
        mock_executor: MagicMock,
        slash_handler: SlashCommandHandler,
        mock_registry: MagicMock,
        mock_rendered_script: RenderedScript,
    ) -> None:
        """Dry-run mode previews without executing."""
        mock_render_fn = MagicMock(return_value=mock_rendered_script)
        mock_processor.process.side_effect = [
            (Session(state=SessionState.SCRIPT_PREVIEW), "脚本..."),
            (Session(state=SessionState.IDLE), "完成"),
        ]
        repl, outputs = make_repl(
            mock_processor,
            mock_executor,
            slash_handler,
            mock_registry,
            inputs=["run it", "/quit"],
            dry_run=True,
            render_fn=mock_render_fn,
        )
        repl.run(Session())

        mock_executor.execute.assert_not_called()
        assert any("dry-run" in o for o in outputs)

    def test_invalid_confirmation_prompts_again(
        self,
        mock_processor: MagicMock,
        mock_executor: MagicMock,
        slash_handler: SlashCommandHandler,
        mock_registry: MagicMock,
        mock_rendered_script: RenderedScript,
    ) -> None:
        """Invalid confirmation prompts again until valid input."""
        mock_render_fn = MagicMock(return_value=mock_rendered_script)
        mock_processor.process.side_effect = [
            (Session(state=SessionState.SCRIPT_PREVIEW), "脚本..."),
            (Session(state=SessionState.IDLE), "完成"),
        ]
        mock_executor.execute.return_value = ExecutionResult(
            success=True, returncode=0, stdout="ok", stderr="", duration_ms=50
        )
        repl, outputs = make_repl(
            mock_processor,
            mock_executor,
            slash_handler,
            mock_registry,
            inputs=["run it", "maybe", "Y", "/quit"],
            render_fn=mock_render_fn,
        )
        repl.run(Session())

        mock_executor.execute.assert_called_once()
        assert any("Y 确认" in o or "N 取消" in o for o in outputs)


class TestREPLExecutionStates:
    """Script execution results and state transitions."""

    def test_success_returns_idle(
        self,
        mock_processor: MagicMock,
        mock_executor: MagicMock,
        slash_handler: SlashCommandHandler,
        mock_registry: MagicMock,
        mock_rendered_script: RenderedScript,
    ) -> None:
        """Successful execution resets session to IDLE."""
        mock_render_fn = MagicMock(return_value=mock_rendered_script)
        mock_processor.process.side_effect = [
            (Session(state=SessionState.SCRIPT_PREVIEW), "脚本..."),
            (Session(state=SessionState.IDLE), "完成"),
        ]
        mock_executor.execute.return_value = ExecutionResult(
            success=True, returncode=0, stdout="ok", stderr="", duration_ms=10
        )
        repl, outputs = make_repl(
            mock_processor,
            mock_executor,
            slash_handler,
            mock_registry,
            inputs=["run it", "Y", "/quit"],
            render_fn=mock_render_fn,
        )
        repl.run(Session())

        assert any("完成" in o for o in outputs)

    def test_failure_enters_error_recovery(
        self,
        mock_processor: MagicMock,
        mock_executor: MagicMock,
        slash_handler: SlashCommandHandler,
        mock_registry: MagicMock,
        mock_rendered_script: RenderedScript,
    ) -> None:
        """Failed execution enters ERROR_RECOVERY state."""
        mock_render_fn = MagicMock(return_value=mock_rendered_script)
        mock_processor.process.side_effect = [
            (Session(state=SessionState.SCRIPT_PREVIEW), "脚本..."),
            (Session(state=SessionState.IDLE), "完成"),
        ]
        mock_executor.execute.return_value = ExecutionResult(
            success=False,
            returncode=1,
            stdout="",
            stderr="file not found",
            duration_ms=10,
        )
        repl, outputs = make_repl(
            mock_processor,
            mock_executor,
            slash_handler,
            mock_registry,
            inputs=["run it", "Y", "/quit"],
            render_fn=mock_render_fn,
        )
        repl.run(Session())

        assert any("失败" in o for o in outputs)

    def test_no_render_fn_skips_execution(
        self,
        mock_processor: MagicMock,
        mock_executor: MagicMock,
        slash_handler: SlashCommandHandler,
        mock_registry: MagicMock,
    ) -> None:
        """If render_fn is None, execution is skipped with a warning."""
        mock_processor.process.side_effect = [
            (Session(state=SessionState.SCRIPT_PREVIEW), "脚本..."),
            (Session(state=SessionState.IDLE), "完成"),
        ]
        repl, outputs = make_repl(
            mock_processor,
            mock_executor,
            slash_handler,
            mock_registry,
            inputs=["run it", "Y", "/quit"],
            render_fn=None,
        )
        repl.run(Session())

        mock_executor.execute.assert_not_called()
        assert any("未配置" in o for o in outputs)


class TestREPLInputOutput:
    """Input/output behaviour."""

    def test_eof_stops_loop(
        self,
        mock_processor: MagicMock,
        mock_executor: MagicMock,
        slash_handler: SlashCommandHandler,
        mock_registry: MagicMock,
    ) -> None:
        """EOF stops the REPL loop cleanly."""
        input_iter = iter([])

        def input_fn(prompt: str = "") -> str:
            raise EOFError()

        outputs: list[str] = []

        def output_fn(text: str) -> None:
            outputs.append(text)

        repl = REPL(
            processor=mock_processor,
            executor=mock_executor,
            slash_handler=slash_handler,
            registry=mock_registry,
            input_fn=input_fn,
            output_fn=output_fn,
        )
        repl.run(Session())

        assert any("再见" in o for o in outputs)

    def test_ctrlc_continues_loop(
        self,
        mock_processor: MagicMock,
        mock_executor: MagicMock,
        slash_handler: SlashCommandHandler,
        mock_registry: MagicMock,
    ) -> None:
        """Ctrl+C (KeyboardInterrupt) continues the loop."""
        call_count = 0

        def input_fn(prompt: str = "") -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise KeyboardInterrupt()
            return "/quit"

        outputs: list[str] = []

        def output_fn(text: str) -> None:
            outputs.append(text)

        repl = REPL(
            processor=mock_processor,
            executor=mock_executor,
            slash_handler=slash_handler,
            registry=mock_registry,
            input_fn=input_fn,
            output_fn=output_fn,
        )
        repl.run(Session())

        assert any("^C" in o or "quit" in o for o in outputs)

    def test_output_fn_property(
        self,
        mock_processor: MagicMock,
        mock_executor: MagicMock,
        slash_handler: SlashCommandHandler,
        mock_registry: MagicMock,
    ) -> None:
        """output_fn property returns the output function."""
        outputs: list[str] = []

        def output_fn(text: str) -> None:
            outputs.append(text)

        repl = REPL(
            processor=mock_processor,
            executor=mock_executor,
            slash_handler=slash_handler,
            registry=mock_registry,
            output_fn=output_fn,
        )
        assert repl.output_fn is output_fn
