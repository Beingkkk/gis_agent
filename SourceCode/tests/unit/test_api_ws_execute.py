"""Tests for api.websocket.execute module.

Design:
    T-UX-05 (DC-UX-05)
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import (
    _reset_dependencies,
    get_session_manager,
    set_template_engine,
    set_workspace,
)
from api.main import create_app
from core.models import ParamDef, SessionState, TemplateDef
from core.workspace import Workspace


@pytest.fixture(autouse=True)
def reset_deps() -> None:
    """Reset global dependencies before each test."""
    _reset_dependencies()


@pytest.fixture
def client() -> TestClient:
    """TestClient with basic app."""
    return TestClient(create_app())


@pytest.fixture
def mock_workspace(tmp_path: pytest.TempPathFactory) -> Workspace:
    """Create a real Workspace in a temp directory."""
    workspace = Workspace(tmp_path)
    set_workspace(workspace)
    return workspace


@pytest.fixture
def mock_template_engine() -> MagicMock:
    """Mock TemplateEngine that returns predictable script content."""
    engine = MagicMock()
    rendered = MagicMock()
    rendered.content = "echo Hello World"
    rendered.platform.name = "WINDOWS"
    engine.render.return_value = rendered
    set_template_engine(engine)
    return engine


class MockStreamReader:
    """Mock asyncio.StreamReader for subprocess stdout/stderr."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = lines
        self._idx = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self._lines):
            raise StopAsyncIteration
        line = self._lines[self._idx]
        self._idx += 1
        return line.encode() if isinstance(line, str) else line

    async def readline(self) -> bytes:
        if self._idx >= len(self._lines):
            return b""
        line = self._lines[self._idx]
        self._idx += 1
        return line.encode() if isinstance(line, str) else line


class MockProcess:
    """Mock asyncio subprocess process for testing."""

    def __init__(
        self,
        stdout_lines: list[str],
        stderr_lines: list[str],
        returncode: int = 0,
        slow_wait: bool = False,
    ) -> None:
        self.stdout = MockStreamReader(stdout_lines)
        self.stderr = MockStreamReader(stderr_lines)
        self._returncode = returncode
        self._killed = False
        self._slow_wait = slow_wait

    async def wait(self) -> int:
        if self._slow_wait and not self._killed:
            await asyncio.sleep(1000)
        return self._returncode

    def kill(self) -> None:
        self._killed = True

    @property
    def returncode(self) -> int:
        return self._returncode


class TestExecuteWebSocket:
    """Tests for /ws/execute/{session_id} WebSocket endpoint."""

    def _create_script_preview_session(self) -> str:
        """Create a session in SCRIPT_PREVIEW state with template and params."""
        session_manager = get_session_manager()
        session_id, session = session_manager.create_session()

        template = TemplateDef(
            id="test_template",
            name="Test Template",
            description="A test template",
            template_file="test.j2",
            params=[
                ParamDef(
                    name="input",
                    type="file_path",
                    required=True,
                    description="Input file",
                ),
            ],
        )

        new_session = (
            session.with_state(SessionState.SCRIPT_PREVIEW)
            .with_template(template)
            .with_param("input", "test.shp")
        )
        session_manager.update_session(session_id, new_session)
        return session_id

    def test_execute_websocket_connect(
        self,
        client: TestClient,
        mock_workspace: Workspace,
        mock_template_engine: MagicMock,
    ) -> None:
        """Client can connect and disconnect cleanly."""
        session_id = self._create_script_preview_session()

        with client.websocket_connect(f"/ws/execute/{session_id}"):
            pass  # Connect and disconnect

    @patch("api.websocket.execute.asyncio.create_subprocess_exec")
    def test_execute_stream_output(
        self,
        mock_create: MagicMock,
        client: TestClient,
        mock_workspace: Workspace,
        mock_template_engine: MagicMock,
    ) -> None:
        """Subprocess stdout is streamed line by line."""
        mock_process = MockProcess(
            stdout_lines=["Line 1", "Line 2"],
            stderr_lines=[],
            returncode=0,
        )
        mock_create.return_value = mock_process

        session_id = self._create_script_preview_session()
        with client.websocket_connect(f"/ws/execute/{session_id}") as ws:
            messages: list[dict] = []
            for _ in range(10):
                msg = ws.receive_json()
                messages.append(msg)
                if msg.get("type") == "done":
                    break

            assert any(
                m.get("type") == "output" and m.get("line") == "Line 1"
                for m in messages
            )
            assert any(
                m.get("type") == "output" and m.get("line") == "Line 2"
                for m in messages
            )
            assert messages[-1] == {
                "type": "done",
                "success": True,
                "returncode": 0,
            }

    @patch("api.websocket.execute.asyncio.create_subprocess_exec")
    def test_execute_done_signal(
        self,
        mock_create: MagicMock,
        client: TestClient,
        mock_workspace: Workspace,
        mock_template_engine: MagicMock,
    ) -> None:
        """Execution completes with done signal including returncode."""
        mock_process = MockProcess(
            stdout_lines=[],
            stderr_lines=[],
            returncode=0,
        )
        mock_create.return_value = mock_process

        session_id = self._create_script_preview_session()
        with client.websocket_connect(f"/ws/execute/{session_id}") as ws:
            msg = ws.receive_json()
            assert msg == {"type": "done", "success": True, "returncode": 0}

    @patch("api.websocket.execute.asyncio.create_subprocess_exec")
    def test_execute_failure_signal(
        self,
        mock_create: MagicMock,
        client: TestClient,
        mock_workspace: Workspace,
        mock_template_engine: MagicMock,
    ) -> None:
        """Failed execution (non-zero exit) sends done with success=false."""
        mock_process = MockProcess(
            stdout_lines=["Some output"],
            stderr_lines=["Error message"],
            returncode=1,
        )
        mock_create.return_value = mock_process

        session_id = self._create_script_preview_session()
        with client.websocket_connect(f"/ws/execute/{session_id}") as ws:
            messages: list[dict] = []
            for _ in range(10):
                msg = ws.receive_json()
                messages.append(msg)
                if msg.get("type") == "done":
                    break

            assert messages[-1]["type"] == "done"
            assert messages[-1]["success"] is False
            assert messages[-1]["returncode"] == 1

    @patch("api.websocket.execute._DEFAULT_TIMEOUT", 0.5)
    @patch("api.websocket.execute.asyncio.create_subprocess_exec")
    def test_execute_timeout(
        self,
        mock_create: MagicMock,
        client: TestClient,
        mock_workspace: Workspace,
        mock_template_engine: MagicMock,
    ) -> None:
        """Timeout sends done with error="timeout" and kills process."""
        mock_process = MockProcess(
            stdout_lines=[],
            stderr_lines=[],
            returncode=-1,
            slow_wait=True,
        )
        mock_create.return_value = mock_process

        session_id = self._create_script_preview_session()
        with client.websocket_connect(f"/ws/execute/{session_id}") as ws:
            messages: list[dict] = []
            for _ in range(10):
                msg = ws.receive_json()
                messages.append(msg)
                if msg.get("type") == "done":
                    break

            assert messages[-1]["type"] == "done"
            assert messages[-1]["success"] is False
            assert messages[-1].get("error") == "timeout"
            assert mock_process._killed is True

    def test_execute_invalid_session(
        self,
        client: TestClient,
        mock_workspace: Workspace,
        mock_template_engine: MagicMock,
    ) -> None:
        """Invalid session_id is rejected with close code 1008."""
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/execute/invalid-session-id"):
                pass

    def test_execute_no_script_preview(
        self,
        client: TestClient,
        mock_workspace: Workspace,
        mock_template_engine: MagicMock,
    ) -> None:
        """Session not in SCRIPT_PREVIEW state sends error and closes."""
        session_manager = get_session_manager()
        session_id, session = session_manager.create_session()
        # Session is in IDLE state, no template selected

        with client.websocket_connect(f"/ws/execute/{session_id}") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "script" in msg.get("message", "").lower()
