"""Tests for ScriptExecutor.

Design: plan-cli v1.0.0 (DC-0063, DC-0064, DC-0065)
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cli.executor import ExecutionResult, ScriptExecutor
from core.workspace import Workspace
from templates.engine import Platform, RenderedScript


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    """Temporary workspace fixture."""
    return Workspace(tmp_path)


@pytest.fixture
def executor(workspace: Workspace) -> ScriptExecutor:
    """ScriptExecutor fixture."""
    return ScriptExecutor(workspace)


@pytest.fixture
def sample_script() -> RenderedScript:
    """Sample rendered script for testing."""
    return RenderedScript(
        content="@echo off\necho hello\n",
        command_lines=["echo hello"],
        platform=Platform.WINDOWS,
        output_path="test.bat",
    )


class TestExecutionResult:
    """ExecutionResult dataclass tests."""

    def test_fields(self) -> None:
        """All fields are present and accessible."""
        result = ExecutionResult(
            success=True,
            returncode=0,
            stdout="output",
            stderr="",
            duration_ms=100,
        )
        assert result.success is True
        assert result.returncode == 0
        assert result.stdout == "output"
        assert result.stderr == ""
        assert result.duration_ms == 100

    def test_frozen(self) -> None:
        """ExecutionResult is frozen."""
        result = ExecutionResult(
            success=True, returncode=0, stdout="", stderr="", duration_ms=0
        )
        with pytest.raises(AttributeError):
            result.success = False  # type: ignore[misc]


class TestScriptExecutorExecute:
    """ScriptExecutor.execute() tests."""

    def test_success_returns_result(
        self,
        executor: ScriptExecutor,
        sample_script: RenderedScript,
    ) -> None:
        """Successful execution returns ExecutionResult with success=True."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "hello\n"
        mock_result.stderr = ""

        with patch("cli.executor.subprocess.run", return_value=mock_result) as mock_run:
            result = executor.execute(sample_script)

        assert isinstance(result, ExecutionResult)
        assert result.success is True
        assert result.returncode == 0
        assert result.stdout == "hello\n"
        assert result.stderr == ""
        assert result.duration_ms >= 0

        # Verify subprocess was called with correct arguments
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["cwd"] == executor._workspace.root
        assert call_kwargs["timeout"] == 300
        assert call_kwargs["capture_output"] is True
        assert call_kwargs["text"] is True

    def test_failure_returns_result(
        self,
        executor: ScriptExecutor,
        sample_script: RenderedScript,
    ) -> None:
        """Non-zero exit code returns ExecutionResult with success=False."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error message\n"

        with patch("cli.executor.subprocess.run", return_value=mock_result):
            result = executor.execute(sample_script)

        assert result.success is False
        assert result.returncode == 1
        assert result.stderr == "error message\n"

    def test_timeout_returns_failure(
        self,
        executor: ScriptExecutor,
        sample_script: RenderedScript,
    ) -> None:
        """TimeoutExpired is caught and returns failure result."""
        with patch(
            "cli.executor.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="test", timeout=300),
        ):
            result = executor.execute(sample_script)

        assert result.success is False
        assert result.returncode == -1
        assert "超时" in result.stderr

    def test_custom_timeout(
        self,
        workspace: Workspace,
        sample_script: RenderedScript,
    ) -> None:
        """Custom timeout is passed to subprocess.run."""
        custom_executor = ScriptExecutor(workspace, timeout=600)
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("cli.executor.subprocess.run", return_value=mock_result) as mock_run:
            custom_executor.execute(sample_script)

        assert mock_run.call_args[1]["timeout"] == 600

    def test_script_written_to_workspace(
        self,
        executor: ScriptExecutor,
        sample_script: RenderedScript,
        workspace: Workspace,
    ) -> None:
        """Script content is written as a temporary file in workspace."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("cli.executor.subprocess.run", return_value=mock_result):
            executor.execute(sample_script)

        # Check that a .bat file was created in workspace
        bat_files = list(workspace.root.glob("*.bat"))
        assert len(bat_files) == 1
        assert bat_files[0].read_text(encoding="utf-8") == sample_script.content

    def test_cwd_is_workspace_root(
        self,
        executor: ScriptExecutor,
        sample_script: RenderedScript,
    ) -> None:
        """subprocess.run is called with cwd=workspace.root."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("cli.executor.subprocess.run", return_value=mock_result) as mock_run:
            executor.execute(sample_script)

        assert mock_run.call_args[1]["cwd"] == executor._workspace.root


class TestScriptExecutorPreview:
    """ScriptExecutor.preview() tests."""

    def test_preview_prints_script(
        self,
        executor: ScriptExecutor,
        sample_script: RenderedScript,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """preview() prints script content without executing."""
        with patch("cli.executor.subprocess.run") as mock_run:
            executor.preview(sample_script)

        mock_run.assert_not_called()
        captured = capsys.readouterr()
        assert sample_script.content in captured.out
