"""Script execution module for GIS Agent.

Executes rendered GDAL scripts via subprocess with workspace isolation
and timeout control.

Design: plan-cli v1.0.0 (DC-0063, DC-0064, DC-0065)
"""

import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from core.workspace import Workspace
from templates.engine import RenderedScript

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExecutionResult:
    """Result of a script execution."""

    success: bool
    returncode: int
    stdout: str
    stderr: str
    duration_ms: int


class ScriptExecutor:
    """Executes rendered GDAL scripts in a workspace-isolated subprocess.

    Design:
        DC-0063, DC-0065
    """

    _DEFAULT_TIMEOUT = 300

    def __init__(
        self,
        workspace: Workspace,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize executor.

        Args:
            workspace: Workspace root used as cwd for script execution.
            timeout: Execution timeout in seconds. Default 300.
        """
        self._workspace = workspace
        self._timeout = timeout

    def execute(self, script: RenderedScript) -> ExecutionResult:
        """Execute a rendered script.

        Writes script content to a temporary file in the workspace,
        then executes it via subprocess.run with timeout.

        Args:
            script: Rendered script to execute.

        Returns:
            ExecutionResult with outcome details.
        """
        # Write script to a temp file in workspace
        script_path = self._write_script_file(script)

        start = time.monotonic()
        try:
            result = subprocess.run(
                ["cmd", "/c", str(script_path)],
                cwd=self._workspace.root,
                timeout=self._timeout,
                capture_output=True,
                text=True,
            )
            duration_ms = int((time.monotonic() - start) * 1000)
            return ExecutionResult(
                success=result.returncode == 0,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                duration_ms=duration_ms,
            )
        except subprocess.TimeoutExpired:
            logger.error("Script execution timed out after %s seconds", self._timeout)
            return ExecutionResult(
                success=False,
                returncode=-1,
                stdout="",
                stderr=f"执行超时（{self._timeout}秒），已终止。",
                duration_ms=int((time.monotonic() - start) * 1000),
            )

    def preview(self, script: RenderedScript) -> None:
        """Print script content without executing.

        Args:
            script: Rendered script to preview.

        Design:
            DC-0064
        """
        print(script.content)

    def _write_script_file(self, script: RenderedScript) -> Path:
        """Write script content to a file in the workspace.

        Returns:
            Path to the written script file.
        """
        ext = ".bat" if script.platform.name == "WINDOWS" else ".sh"
        # Use a timestamped filename to avoid collisions
        timestamp = str(int(time.time()))
        filename = f"script_{timestamp}{ext}"
        script_path = self._workspace.root / filename
        script_path.write_text(script.content, encoding="utf-8")
        logger.debug("Script written to %s", script_path)
        return script_path
