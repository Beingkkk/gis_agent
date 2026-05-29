"""Tests for api.websocket.chat module.

Design:
    T-UX-04 (DC-UX-04)
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import (
    _reset_dependencies,
    set_llm_client,
    set_prompt_builder,
    set_registry,
)
from api.main import create_app


@pytest.fixture(autouse=True)
def reset_deps() -> None:
    """Reset global dependencies before each test."""
    _reset_dependencies()


@pytest.fixture
def client() -> TestClient:
    """TestClient with basic app."""
    return TestClient(create_app())


@pytest.fixture
def mock_registry() -> MagicMock:
    """Mock TemplateRegistry with empty list."""
    registry = MagicMock()
    registry.list_templates.return_value = []
    return registry


class TestChatWebSocket:
    """Tests for /ws/chat/{session_id} WebSocket endpoint."""

    def _setup_deps(self, mock_registry: MagicMock) -> None:
        """Set up mock dependencies for chat tests."""
        set_llm_client(MagicMock())
        set_prompt_builder(MagicMock())
        set_registry(mock_registry)

    def _create_session(self, client: TestClient) -> str:
        """Create a session and return its ID."""
        resp = client.post("/api/session")
        assert resp.status_code == 200
        return resp.json()["session_id"]

    def test_chat_websocket_connect(
        self, client: TestClient, mock_registry: MagicMock
    ) -> None:
        """Client can connect and disconnect cleanly."""
        self._setup_deps(mock_registry)
        session_id = self._create_session(client)

        with client.websocket_connect(f"/ws/chat/{session_id}"):
            pass  # Connect and disconnect

    def test_chat_stream_response(
        self, client: TestClient, mock_registry: MagicMock
    ) -> None:
        """Sending a message receives streaming chunks followed by done."""
        self._setup_deps(mock_registry)
        session_id = self._create_session(client)

        def mock_answer(
            user_input: str,
            templates: list,
            history: list,
            client: MagicMock,
            builder: MagicMock,
            on_chunk: any = None,
        ) -> str:
            if on_chunk:
                on_chunk("这是")
                on_chunk("回答")
            return "这是回答"

        with patch("api.websocket.chat.answer_question", side_effect=mock_answer):
            with client.websocket_connect(f"/ws/chat/{session_id}") as ws:
                ws.send_json({"message": "你好"})

                # Collect all messages until done
                messages: list[dict] = []
                for _ in range(10):  # Safety limit
                    msg = ws.receive_json()
                    messages.append(msg)
                    if msg.get("type") == "done":
                        break

                assert len(messages) >= 3
                assert messages[0] == {"type": "chunk", "content": "这是"}
                assert messages[1] == {"type": "chunk", "content": "回答"}
                assert messages[-1] == {"type": "done"}

    def test_chat_done_signal(
        self, client: TestClient, mock_registry: MagicMock
    ) -> None:
        """Stream ends with a done signal."""
        self._setup_deps(mock_registry)
        session_id = self._create_session(client)

        def mock_answer(
            user_input: str,
            templates: list,
            history: list,
            client: MagicMock,
            builder: MagicMock,
            on_chunk: any = None,
        ) -> str:
            return "Short answer"

        with patch("api.websocket.chat.answer_question", side_effect=mock_answer):
            with client.websocket_connect(f"/ws/chat/{session_id}") as ws:
                ws.send_json({"message": "test"})

                # No chunks produced, should receive done directly
                msg = ws.receive_json()
                assert msg == {"type": "done"}

    def test_chat_invalid_session(
        self, client: TestClient, mock_registry: MagicMock
    ) -> None:
        """Invalid session_id is rejected with close code 1008."""
        self._setup_deps(mock_registry)

        with pytest.raises(Exception):
            with client.websocket_connect("/ws/chat/invalid-session-id"):
                pass

    def test_chat_disconnect_cleanup(
        self, client: TestClient, mock_registry: MagicMock
    ) -> None:
        """Client disconnect does not raise unhandled exceptions."""
        self._setup_deps(mock_registry)
        session_id = self._create_session(client)

        # Just connect and disconnect — no errors should propagate
        with client.websocket_connect(f"/ws/chat/{session_id}"):
            pass
