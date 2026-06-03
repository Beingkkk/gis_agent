"""Tests for api.websocket.generator module.

Design:
    DC-0096
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import _reset_dependencies, set_llm_client
from api.main import create_app


@pytest.fixture(autouse=True)
def reset_deps() -> None:
    """Reset global dependencies before each test."""
    _reset_dependencies()


@pytest.fixture
def client() -> TestClient:
    """TestClient with basic app."""
    return TestClient(create_app())


class TestGeneratorWebSocket:
    """Tests for /ws/generator/generate WebSocket endpoint."""

    def test_ws_stream_chunks_and_done(self, client: TestClient) -> None:
        """WebSocket streams chunks then sends done with parsed result."""
        llm_client = MagicMock()
        llm_client.chat_stream.return_value = iter([
            '{"template_id": ',
            '"test_ws", ',
            '"name": "WS Test", ',
            '"description": "A test", ',
            '"body": "echo {{ input }}", ',
            '"params": [{"name": "input", "type": "file_path", "required": true}], ',
            '"concepts": [], ',
            '"notes": []}',
        ])
        set_llm_client(llm_client)

        with client.websocket_connect("/ws/generator/generate") as ws:
            ws.send_json({
                "type": "start",
                "document_text": "Simple test tool",
                "config": {"category": "general"},
            })

            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] in ("done", "error"):
                    break

            # Should have received chunks + done
            chunk_messages = [m for m in messages if m["type"] == "chunk"]
            assert len(chunk_messages) > 0

            done_messages = [m for m in messages if m["type"] == "done"]
            assert len(done_messages) == 1
            result = done_messages[0]["result"]
            assert result["template_id"] == "test_ws"
            assert result["name"] == "WS Test"
            assert "body" in result
            assert "params" in result

    def test_ws_done_with_command_template_fallback(self, client: TestClient) -> None:
        """LLM output 'command_template'/'id' maps to assembled .j2 body."""
        llm_client = MagicMock()
        llm_client.chat_stream.return_value = iter([
            '{"id": "carto_import", ',
            '"name": "Carto Import", ',
            '"description": "Import to Carto", ',
            '"command_template": "ogr2ogr -f Carto {{ output }} {{ input }}", ',
            '"params": [{"name": "input", "type": "file_path", "required": true}], ',
            '"concepts": [], ',
            '"notes": []}',
        ])
        set_llm_client(llm_client)

        with client.websocket_connect("/ws/generator/generate") as ws:
            ws.send_json({
                "type": "start",
                "document_text": "Carto import tool",
                "config": {"category": "vector"},
            })

            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] in ("done", "error"):
                    break

            done_messages = [m for m in messages if m["type"] == "done"]
            assert len(done_messages) == 1
            result = done_messages[0]["result"]
            assert result["template_id"] == "carto_import"
            # Body is now assembled full .j2, not raw command_template
            assert "{# @id carto_import #}" in result["body"]
            assert "@echo off" in result["body"]
            assert "ogr2ogr -f Carto {{ output }} {{ input }}" in result["body"]

    def test_ws_error_on_token_budget(self, client: TestClient) -> None:
        """Document exceeding token budget returns error frame."""
        llm_client = MagicMock()
        set_llm_client(llm_client)

        long_text = "x" * 50000  # ~12500 tokens, exceeds 12000 limit

        with client.websocket_connect("/ws/generator/generate") as ws:
            ws.send_json({
                "type": "start",
                "document_text": long_text,
                "config": {},
            })

            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "validation" in msg.get("stage", "")
            assert "过长" in msg["message"] or "tokens" in msg["message"].lower()

    def test_ws_error_on_parse_failure(self, client: TestClient) -> None:
        """LLM output that is not valid JSON returns error frame."""
        llm_client = MagicMock()
        llm_client.chat_stream.return_value = iter([
            "this is not json at all",
        ])
        # Retry also returns invalid JSON so both attempts fail
        llm_client.chat.return_value = "still not invalid json"
        set_llm_client(llm_client)

        with client.websocket_connect("/ws/generator/generate") as ws:
            ws.send_json({
                "type": "start",
                "document_text": "Broken tool",
                "config": {},
            })

            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] in ("done", "error"):
                    break

            error_messages = [m for m in messages if m["type"] == "error"]
            assert len(error_messages) == 1
            assert "parsing" in error_messages[0].get("stage", "")

    def test_ws_error_on_empty_document(self, client: TestClient) -> None:
        """Empty document_text returns validation error."""
        llm_client = MagicMock()
        set_llm_client(llm_client)

        with client.websocket_connect("/ws/generator/generate") as ws:
            ws.send_json({
                "type": "start",
                "document_text": "",
                "config": {},
            })

            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "validation" in msg.get("stage", "")

    def test_ws_error_on_invalid_protocol(self, client: TestClient) -> None:
        """Message without 'type': 'start' returns protocol error."""
        llm_client = MagicMock()
        set_llm_client(llm_client)

        with client.websocket_connect("/ws/generator/generate") as ws:
            ws.send_json({"foo": "bar"})

            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "protocol" in msg.get("stage", "")
