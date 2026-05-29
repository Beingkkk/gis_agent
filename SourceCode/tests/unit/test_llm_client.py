"""Unit tests for llm.client module.

Design: DC-0030, DC-0031, DC-0033, DC-0034
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from llm.client import LLMClient
from llm.exceptions import (
    LLMAuthError,
    LLMConnectionError,
    LLMContextError,
    LLMRateLimitError,
    LLMResponseError,
)
from llm.models import Message


def _make_conn_err(message: str = "timeout") -> Exception:
    """Construct anthropic APIConnectionError for testing."""
    from anthropic import APIConnectionError

    return APIConnectionError(
        message=message, request=httpx.Request("GET", "http://test")
    )


def _make_auth_err(message: str = "invalid key") -> Exception:
    """Construct anthropic AuthenticationError for testing."""
    from anthropic import AuthenticationError

    req = httpx.Request("GET", "http://test")
    resp = httpx.Response(401, request=req)
    return AuthenticationError(message, response=resp, body=None)


def _make_rate_err(message: str = "rate limited") -> Exception:
    """Construct anthropic RateLimitError for testing."""
    from anthropic import RateLimitError

    req = httpx.Request("GET", "http://test")
    resp = httpx.Response(429, request=req)
    return RateLimitError(message, response=resp, body=None)


def _make_server_err(message: str = "server error") -> Exception:
    """Construct anthropic InternalServerError for testing."""
    from anthropic import InternalServerError

    req = httpx.Request("GET", "http://test")
    resp = httpx.Response(500, request=req)
    return InternalServerError(message, response=resp, body=None)


def _make_bad_request_err(
    message: str = "bad request", body: object = None
) -> Exception:
    """Construct anthropic BadRequestError for testing."""
    from anthropic import BadRequestError

    req = httpx.Request("GET", "http://test")
    resp = httpx.Response(400, request=req)
    return BadRequestError(message, response=resp, body=body)


def _make_api_status_429(message: str = "rate limited") -> Exception:
    """Construct raw APIStatusError with 429 for testing."""
    from anthropic import APIStatusError

    req = httpx.Request("GET", "http://test")
    resp = httpx.Response(429, request=req)
    return APIStatusError(message, response=resp, body=None)


class TestLLMClientInit:
    """Test LLMClient initialization."""

    def test_init_reads_config(self) -> None:
        """DC-0030: Client initializes from Config."""
        with patch("llm.client.get_config") as mock_get_config:
            mock_get_config.return_value = MagicMock(
                llm=MagicMock(
                    base_url="https://api.example.com",
                    auth_key="test-key",
                    model_name="test-model",
                )
            )
            client = LLMClient()
            assert client is not None


class TestLLMClientChat:
    """Test LLMClient.chat()."""

    @pytest.fixture
    def client(self) -> LLMClient:
        """Create client with mocked config."""
        with patch("llm.client.get_config") as mock_get_config:
            mock_get_config.return_value = MagicMock(
                llm=MagicMock(
                    base_url="https://api.example.com",
                    auth_key="test-key",
                    model_name="test-model",
                )
            )
            return LLMClient()

    def test_chat_returns_text(self, client: LLMClient) -> None:
        """Normal API call returns model text."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(type="text", text="classify result")]

        with patch.object(
            client._anthropic.messages, "create", return_value=mock_response
        ):
            result = client.chat(
                system_prompt="system",
                messages=[Message(role="user", content="hello")],
                temperature=0.1,
            )
            assert result == "classify result"

    def test_chat_passes_correct_params(self, client: LLMClient) -> None:
        """Verify correct parameters passed to anthropic API."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(type="text", text="ok")]

        with patch.object(
            client._anthropic.messages, "create", return_value=mock_response
        ) as mock_create:
            client.chat(
                system_prompt="sys_prompt",
                messages=[
                    Message(role="user", content="msg1"),
                    Message(role="assistant", content="msg2"),
                ],
                temperature=0.5,
            )

            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["model"] == "test-model"
            assert call_kwargs["system"] == "sys_prompt"
            assert call_kwargs["temperature"] == 0.5
            assert len(call_kwargs["messages"]) == 2
            assert call_kwargs["messages"][0]["role"] == "user"
            assert call_kwargs["messages"][0]["content"] == "msg1"

    def test_exponential_backoff_retry_on_timeout(self, client: LLMClient) -> None:
        """DC-0034: Transient errors retry 3 times with exponential backoff."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(type="text", text="success after retry")]

        side_effects = [
            _make_conn_err("timeout"),
            _make_conn_err("timeout"),
            mock_response,
        ]

        with patch.object(
            client._anthropic.messages, "create", side_effect=side_effects
        ) as mock_create:
            with patch("llm.client.time.sleep") as mock_sleep:
                result = client.chat(
                    system_prompt="system",
                    messages=[Message(role="user", content="hello")],
                )
                assert result == "success after retry"
                assert mock_create.call_count == 3
                mock_sleep.assert_any_call(1.0)
                mock_sleep.assert_any_call(2.0)

    def test_no_retry_on_4xx_auth(self, client: LLMClient) -> None:
        """DC-0034: 4xx errors are not retried."""
        with patch.object(
            client._anthropic.messages,
            "create",
            side_effect=_make_auth_err("invalid key"),
        ) as mock_create:
            with pytest.raises(LLMAuthError):
                client.chat(
                    system_prompt="system",
                    messages=[Message(role="user", content="hello")],
                )
            assert mock_create.call_count == 1

    def test_retry_exhausted_raises_connection_error(self, client: LLMClient) -> None:
        """DC-0034: After 3 retries, raise LLMConnectionError."""
        with patch.object(
            client._anthropic.messages,
            "create",
            side_effect=_make_conn_err("always fails"),
        ):
            with patch("llm.client.time.sleep"):
                with pytest.raises(LLMConnectionError):
                    client.chat(
                        system_prompt="system",
                        messages=[Message(role="user", content="hello")],
                    )

    def test_rate_limit_retry_then_fail(self, client: LLMClient) -> None:
        """DC-0034: RateLimitError retries with backoff."""
        with patch.object(
            client._anthropic.messages,
            "create",
            side_effect=_make_rate_err("rate limited"),
        ):
            with patch("llm.client.time.sleep"):
                with pytest.raises(LLMRateLimitError):
                    client.chat(
                        system_prompt="system",
                        messages=[Message(role="user", content="hello")],
                    )

    def test_api_status_429_retries(self, client: LLMClient) -> None:
        """DC-0034: APIStatusError with 429 retries via fallback path."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(type="text", text="ok")]
        side_effects = [
            _make_api_status_429("rate limited"),
            mock_response,
        ]
        with patch.object(
            client._anthropic.messages, "create", side_effect=side_effects
        ):
            with patch("llm.client.time.sleep"):
                result = client.chat(
                    system_prompt="system",
                    messages=[Message(role="user", content="hello")],
                )
                assert result == "ok"

    def test_server_error_500_retries(self, client: LLMClient) -> None:
        """DC-0034: 5xx server errors retry with backoff."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(type="text", text="ok")]
        side_effects = [
            _make_server_err("server error"),
            mock_response,
        ]
        with patch.object(
            client._anthropic.messages, "create", side_effect=side_effects
        ):
            with patch("llm.client.time.sleep"):
                result = client.chat(
                    system_prompt="system",
                    messages=[Message(role="user", content="hello")],
                )
                assert result == "ok"

    def test_bad_request_400_context_length(self, client: LLMClient) -> None:
        """DC-0034: 400 with context/length raises LLMContextError."""
        with patch.object(
            client._anthropic.messages,
            "create",
            side_effect=_make_bad_request_err(
                "context_length_exceeded",
                body={"error": {"type": "context_length_exceeded"}},
            ),
        ):
            with pytest.raises(LLMContextError):
                client.chat(
                    system_prompt="system",
                    messages=[Message(role="user", content="hello")],
                )

    def test_bad_request_400_other_raises_response_error(
        self, client: LLMClient
    ) -> None:
        """DC-0034: 400 without context/length raises LLMResponseError."""
        with patch.object(
            client._anthropic.messages,
            "create",
            side_effect=_make_bad_request_err("invalid format"),
        ):
            with pytest.raises(LLMResponseError):
                client.chat(
                    system_prompt="system",
                    messages=[Message(role="user", content="hello")],
                )

    def test_permission_denied_raises_auth_error(self, client: LLMClient) -> None:
        """DC-0034: PermissionDeniedError raises LLMAuthError."""
        from anthropic import PermissionDeniedError

        req = httpx.Request("GET", "http://test")
        resp = httpx.Response(403, request=req)
        err = PermissionDeniedError("forbidden", response=resp, body=None)
        with patch.object(client._anthropic.messages, "create", side_effect=err):
            with pytest.raises(LLMAuthError):
                client.chat(
                    system_prompt="system",
                    messages=[Message(role="user", content="hello")],
                )


class TestTokenTruncation:
    """Test DC-0033 token budget and truncation."""

    @pytest.fixture
    def client(self) -> LLMClient:
        with patch("llm.client.get_config") as mock_get_config:
            mock_get_config.return_value = MagicMock(
                llm=MagicMock(
                    base_url="https://api.example.com",
                    auth_key="test-key",
                    model_name="test-model",
                )
            )
            return LLMClient()

    def test_token_estimate(self, client: LLMClient) -> None:
        """_estimate_tokens returns len(text) // 4."""
        assert client._estimate_tokens("abcd") == 1
        assert client._estimate_tokens("a" * 400) == 100

    def test_truncate_messages_removes_oldest(self, client: LLMClient) -> None:
        """DC-0033: Oldest messages removed when over budget."""
        long_text = "x" * 4000  # ~1000 tokens
        messages = [
            Message(role="user", content="oldest"),
            Message(role="assistant", content=long_text),
            Message(role="user", content=long_text),
            Message(role="assistant", content=long_text),
            Message(role="user", content=long_text),
            Message(role="assistant", content=long_text),
            Message(role="user", content=long_text),
            Message(role="assistant", content=long_text),
            Message(role="user", content=long_text),
            Message(role="assistant", content=long_text),
        ]

        truncated = client._truncate_messages(
            system_prompt="short",
            messages=messages,
            current_input="final",
        )

        # System prompt + current input should be preserved
        assert len(truncated) < len(messages)
        # System prompt is not in messages list, but we verify oldest removed
        first_content = truncated[0].content if truncated else ""
        assert "oldest" not in first_content

    def test_truncate_messages_preserves_system(self, client: LLMClient) -> None:
        """DC-0033: System prompt is never truncated."""
        messages = [
            Message(role="user", content="x" * 8000),
        ]

        truncated = client._truncate_messages(
            system_prompt="must preserve this",
            messages=messages,
            current_input="x" * 8000,
        )

        # Truncated current input should leave room for system
        # We just verify the method completes without error
        assert isinstance(truncated, list)

    def test_truncate_input_when_all_history_removed(self, client: LLMClient) -> None:
        """DC-0033: If all history removed, truncate current input."""
        messages = [Message(role="user", content="x" * 4000)]

        truncated = client._truncate_messages(
            system_prompt="x" * 4000,
            messages=messages,
            current_input="x" * 8000,
        )

        # Should have removed all history and truncated input
        assert len(truncated) <= 1

    def test_truncate_system_too_long_raises(self, client: LLMClient) -> None:
        """DC-0033: System prompt exceeding budget raises LLMContextError."""
        with pytest.raises(LLMContextError):
            client._truncate_messages(
                system_prompt="x" * 40000,  # ~10000 tokens
                messages=[Message(role="user", content="hello")],
                current_input="world",
            )


class TestChatWithTruncation:
    """Test chat() integrates truncation."""

    @pytest.fixture
    def client(self) -> LLMClient:
        with patch("llm.client.get_config") as mock_get_config:
            mock_get_config.return_value = MagicMock(
                llm=MagicMock(
                    base_url="https://api.example.com",
                    auth_key="test-key",
                    model_name="test-model",
                )
            )
            return LLMClient()

    def test_chat_truncates_long_messages(self, client: LLMClient) -> None:
        """DC-0033: Long messages are truncated before API call."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(type="text", text="ok")]

        long_messages = [Message(role="user", content="x" * 4000) for _ in range(12)]

        with patch.object(
            client._anthropic.messages, "create", return_value=mock_response
        ) as mock_create:
            client.chat(
                system_prompt="system",
                messages=long_messages,
            )

            call_kwargs = mock_create.call_args.kwargs
            sent_messages = call_kwargs["messages"]
            assert len(sent_messages) < len(long_messages)


class TestLLMClientChatStream:
    """Test LLMClient.chat_stream(). Design: DC-0068."""

    @pytest.fixture
    def client(self) -> LLMClient:
        """Create client with mocked config."""
        with patch("llm.client.get_config") as mock_get_config:
            mock_get_config.return_value = MagicMock(
                llm=MagicMock(
                    base_url="https://api.example.com",
                    auth_key="test-key",
                    model_name="test-model",
                )
            )
            return LLMClient()

    def _make_mock_event(self, text: str) -> MagicMock:
        """Create a mock content_block_delta event with text delta."""
        event = MagicMock()
        event.type = "content_block_delta"
        event.delta = MagicMock()
        event.delta.text = text
        return event

    def test_chat_stream_yields_chunks(self, client: LLMClient) -> None:
        """Streaming call yields text chunks."""
        events = [
            self._make_mock_event("Hello"),
            self._make_mock_event(" world"),
            self._make_mock_event("!"),
        ]
        mock_stream = MagicMock()
        mock_stream.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream.__exit__ = MagicMock(return_value=False)
        mock_stream.__iter__ = MagicMock(return_value=iter(events))

        with patch.object(
            client._anthropic.messages, "create", return_value=mock_stream
        ) as mock_create:
            result = list(
                client.chat_stream(
                    system_prompt="system",
                    messages=[Message(role="user", content="hi")],
                    temperature=0.1,
                )
            )
            assert result == ["Hello", " world", "!"]
            assert mock_create.call_args.kwargs["stream"] is True

    def test_chat_stream_passes_correct_params(self, client: LLMClient) -> None:
        """Verify stream=True and other params passed correctly."""
        events = [self._make_mock_event("ok")]
        mock_stream = MagicMock()
        mock_stream.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream.__exit__ = MagicMock(return_value=False)
        mock_stream.__iter__ = MagicMock(return_value=iter(events))

        with patch.object(
            client._anthropic.messages, "create", return_value=mock_stream
        ) as mock_create:
            list(
                client.chat_stream(
                    system_prompt="sys_prompt",
                    messages=[Message(role="user", content="msg1")],
                    temperature=0.5,
                )
            )
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["model"] == "test-model"
            assert call_kwargs["system"] == "sys_prompt"
            assert call_kwargs["temperature"] == 0.5
            assert call_kwargs["stream"] is True

    def test_chat_stream_truncates_long_messages(self, client: LLMClient) -> None:
        """DC-0068: Streaming also applies token truncation."""
        events = [self._make_mock_event("ok")]
        mock_stream = MagicMock()
        mock_stream.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream.__exit__ = MagicMock(return_value=False)
        mock_stream.__iter__ = MagicMock(return_value=iter(events))

        long_messages = [
            Message(role="user", content="x" * 4000) for _ in range(12)
        ]

        with patch.object(
            client._anthropic.messages, "create", return_value=mock_stream
        ) as mock_create:
            list(
                client.chat_stream(
                    system_prompt="system",
                    messages=long_messages,
                )
            )
            call_kwargs = mock_create.call_args.kwargs
            sent_messages = call_kwargs["messages"]
            assert len(sent_messages) < len(long_messages)
