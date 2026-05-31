"""Execute WebSocket handler.

Provides real-time script execution log streaming over WebSocket
using asyncio subprocess.

Design:
    T-UX-05 (DC-UX-05)
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from api.dependencies import (
    get_session_manager,
    get_template_engine,
    get_workspace,
)
from core.models import ExecutionErrorContext, SessionState

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 300


async def handle_execute_websocket(websocket: WebSocket, session_id: str) -> None:
    """Handle a script execution WebSocket connection.

    Validates session, renders the script from template + params,
    executes via subprocess, and streams stdout/stderr lines back
    as ``{"type": "output", "line": "...", "stream": "stdout"}``
    frames, followed by ``{"type": "done", "success": true/false}``.

    On failure, updates session state to ERROR_RECOVERY with error_context.
    On success, resets session state to IDLE.

    Args:
        websocket: FastAPI WebSocket instance.
        session_id: Session UUID from URL path.
    """
    session_manager = get_session_manager()
    session = session_manager.get_session(session_id)

    # Validate session before accepting
    if session is None:
        await websocket.close(code=1008, reason="Invalid session")
        return

    # Must have a script ready to execute
    if session.state != SessionState.SCRIPT_PREVIEW or session.template is None:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "No script to execute"})
        await websocket.close()
        return

    await websocket.accept()

    # Render script from template + params
    engine = get_template_engine()
    try:
        rendered = engine.render(session.template, session.params)
    except Exception as exc:
        logger.exception("Script render error: %s", exc)
        await websocket.send_json({"type": "done", "success": False, "error": str(exc)})
        return

    # Write script to temp file in workspace
    workspace = get_workspace()
    script_path = _write_script_file(rendered, workspace)

    # Execute with streaming
    try:
        process = await asyncio.create_subprocess_exec(
            "cmd",
            "/c",
            str(script_path),
            cwd=str(workspace.root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except Exception as exc:
        logger.exception("Failed to start subprocess: %s", exc)
        await websocket.send_json({"type": "done", "success": False, "error": str(exc)})
        return

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    start_time = time.time()

    async def _stream_output(
        stream: asyncio.StreamReader, stream_name: str, collector: list[str]
    ) -> None:
        """Read lines from stream, collect for error context, and send via WebSocket."""
        while True:
            line_bytes = await stream.readline()
            if not line_bytes:
                break
            line = line_bytes.decode("utf-8", errors="replace").rstrip("\n")
            collector.append(line)
            await websocket.send_json(
                {"type": "output", "line": line, "stream": stream_name}
            )

    # Start stdout/stderr readers concurrently
    if process.stdout is None or process.stderr is None:
        await websocket.send_json(
            {
                "type": "done",
                "success": False,
                "error": "Failed to open subprocess pipes",
            }
        )
        return

    stdout_task = asyncio.create_task(
        _stream_output(process.stdout, "stdout", stdout_lines)
    )
    stderr_task = asyncio.create_task(
        _stream_output(process.stderr, "stderr", stderr_lines)
    )

    try:
        # Wait for process completion with timeout
        returncode = await asyncio.wait_for(process.wait(), timeout=_DEFAULT_TIMEOUT)
        # Ensure readers finish (drain remaining output)
        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
        duration_ms = int((time.time() - start_time) * 1000)

        # Update session state based on execution result
        if returncode == 0:
            # Success → IDLE (execution breakpoint: full reset per DC-0067)
            new_session = (
                session.with_state(SessionState.IDLE)
                .clear_history()
                .clear_error()
            )
            session_manager.update_session(session_id, new_session)
            logger.info(
                "Execution succeeded (session=%s, duration=%dms)",
                session_id,
                duration_ms,
            )
        else:
            # Failure → ERROR_RECOVERY with error context
            error_ctx = ExecutionErrorContext(
                returncode=returncode,
                stdout="\n".join(stdout_lines),
                stderr="\n".join(stderr_lines),
                duration_ms=duration_ms,
            )
            new_session = (
                session.with_state(SessionState.ERROR_RECOVERY)
                .with_error(error_ctx)
            )
            session_manager.update_session(session_id, new_session)
            logger.warning(
                "Execution failed (session=%s, rc=%d, duration=%dms)",
                session_id,
                returncode,
                duration_ms,
            )

        await websocket.send_json(
            {"type": "done", "success": returncode == 0, "returncode": returncode}
        )
    except asyncio.TimeoutError:
        logger.error("Script execution timed out after %s seconds", _DEFAULT_TIMEOUT)
        try:
            process.kill()
            await process.wait()
        except Exception:
            pass
        stdout_task.cancel()
        stderr_task.cancel()
        duration_ms = int((time.time() - start_time) * 1000)
        # Timeout → ERROR_RECOVERY
        error_ctx = ExecutionErrorContext(
            returncode=-1,
            stdout="\n".join(stdout_lines),
            stderr="Execution timed out after {} seconds".format(_DEFAULT_TIMEOUT),
            duration_ms=duration_ms,
        )
        new_session = (
            session.with_state(SessionState.ERROR_RECOVERY)
            .with_error(error_ctx)
        )
        session_manager.update_session(session_id, new_session)
        try:
            await websocket.send_json(
                {"type": "done", "success": False, "error": "timeout"}
            )
        except Exception:
            pass
    except WebSocketDisconnect:
        logger.debug("Execute WebSocket disconnected: %s", session_id)
        try:
            process.kill()
            await process.wait()
        except Exception:
            pass
        stdout_task.cancel()
        stderr_task.cancel()
    except Exception as exc:
        logger.exception("Execute WebSocket error: %s", exc)
        try:
            process.kill()
            await process.wait()
        except Exception:
            pass
        stdout_task.cancel()
        stderr_task.cancel()
        try:
            await websocket.send_json(
                {"type": "done", "success": False, "error": str(exc)}
            )
        except Exception:
            pass


def _write_script_file(rendered: Any, workspace: Any) -> Path:
    """Write rendered script content to a temp file in workspace.

    Args:
        rendered: Rendered script object with ``content`` and ``platform``.
        workspace: Workspace instance.

    Returns:
        Path to the written script file.
    """
    ext = ".bat" if rendered.platform.name == "WINDOWS" else ".sh"
    timestamp = str(int(time.time()))
    filename = f"script_{timestamp}{ext}"
    script_path = Path(workspace.root) / filename
    script_path.write_text(rendered.content, encoding="utf-8")
    logger.debug("Script written to %s", script_path)
    return script_path
