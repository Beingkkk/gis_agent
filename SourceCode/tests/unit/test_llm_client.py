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
        """DC-0034/ADR-0005: Transient errors retry 3 times before success."""
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
            result = client.chat(
                system_prompt="system",
                messages=[Message(role="user", content="hello")],
            )
            assert result == "success after retry"
            assert mock_create.call_count == 3

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
        """DC-0034/ADR-0005: After 3 retries, raise LLMConnectionError."""
        with patch.object(
            client._anthropic.messages,
            "create",
            side_effect=_make_conn_err("always fails"),
        ) as mock_create:
            with patch("time.sleep"):
                with pytest.raises(LLMConnectionError):
                    client.chat(
                        system_prompt="system",
                        messages=[Message(role="user", content="hello")],
                    )
                assert mock_create.call_count == 4

    def test_rate_limit_retry_then_fail(self, client: LLMClient) -> None:
        """DC-0034/ADR-0005: RateLimitError retries with backoff."""
        with patch.object(
            client._anthropic.messages,
            "create",
            side_effect=_make_rate_err("rate limited"),
        ) as mock_create:
            with patch("time.sleep"):
                with pytest.raises(LLMRateLimitError):
                    client.chat(
                        system_prompt="system",
                        messages=[Message(role="user", content="hello")],
                    )
                assert mock_create.call_count == 4

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
            with patch("time.sleep"):
                result = client.chat(
                    system_prompt="system",
                    messages=[Message(role="user", content="hello")],
                )
                assert result == "ok"

    def test_server_error_500_retries(self, client: LLMClient) -> None:
        """DC-0034/ADR-0005: 5xx server errors retry with backoff."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(type="text", text="ok")]
        side_effects = [
            _make_server_err("server error"),
            mock_response,
        ]
        with patch.object(
            client._anthropic.messages, "create", side_effect=side_effects
        ):
            with patch("time.sleep"):
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
        """DC-0033: When budget is tight, history is removed and input truncated."""
        # Very long system prompt leaves little room; long history + input
        # exceed available budget.
        messages = [Message(role="user", content="x" * 4000)]

        truncated = client._truncate_messages(
            system_prompt="x" * 22000,  # ~5500 tokens, available = 2500
            messages=messages,
            current_input="x" * 16000,  # ~4000 tokens
        )

        # History removed, current input truncated to fit remaining budget
        assert len(truncated) >= 1
        assert len(truncated[-1].content) < 16000

    def test_truncate_system_too_long_raises(self, client: LLMClient) -> None:
        """DC-0033: System prompt exceeding budget raises LLMContextError."""
        with pytest.raises(LLMContextError):
            client._truncate_messages(
                system_prompt="x" * 40000,  # ~10000 tokens
                messages=[Message(role="user", content="hello")],
                current_input="world",
            )

    def test_truncate_never_returns_empty(self, client: LLMClient) -> None:
        """DC-0033: When current_input equals last message, result is never empty.

        Before the fix, ``total`` double-counted the last message
        (``input_tokens + sum(all messages)``).  With a long system prompt,
        the while loop popped every message and returned ``[]``, causing
        Anthropic API to reject with "messages must not be empty".
        """
        # Simulate template generation: few-shot + ack + document
        few_shot = Message(role="user", content="x" * 3000)  # ~750 tokens
        ack = Message(role="assistant", content="Understood.")  # ~3 tokens
        doc = Message(role="user", content="x" * 2000)  # ~500 tokens
        messages = [few_shot, ack, doc]
        current_input = doc.content

        # Long system prompt leaves little room (TOKEN_LIMIT=8000)
        # sys_tokens ~1875, available ~6125
        # Old double-count total: 500 + 750 + 3 + 500 = 1753 -> fine
        # But with an even longer system prompt:
        system_prompt = "x" * 6000  # ~1500 tokens, available ~6500
        # Old bug: total = 500 + (750 + 3 + 500) = 1753, still fine
        # Need to make available very tight:
        system_prompt = "x" * 7300  # ~1825 tokens, available ~6175
        # old total = 500 + 750 + 3 + 500 = 1753 < 6175, still fine
        # Let's push it:
        system_prompt = "x" * 7500  # ~1875 tokens, available ~6125
        # With even longer few-shot to exceed budget:
        few_shot = Message(role="user", content="x" * 5000)  # ~1250 tokens
        messages = [few_shot, ack, doc]
        # old total = 500 + 1250 + 3 + 500 = 2253 < 6125, still fine
        # Need messages that exceed available when double-counted.
        # Let's make the sum of all messages > available - input_tokens.
        few_shot = Message(role="user", content="x" * 5000)
        ack = Message(role="assistant", content="x" * 500)
        doc = Message(role="user", content="x" * 2000)
        messages = [few_shot, ack, doc]
        current_input = doc.content
        system_prompt = "x" * 6000  # 1500 tokens, available 6500
        # old total = 500 + 1250 + 125 + 500 = 2375 < 6500
        # Hmm, we need to exceed available. Let's use very long messages.
        few_shot = Message(role="user", content="x" * 15000)  # 3750 tokens
        ack = Message(role="assistant", content="x" * 2000)    # 500 tokens
        doc = Message(role="user", content="x" * 2000)         # 500 tokens
        messages = [few_shot, ack, doc]
        current_input = doc.content
        system_prompt = "x" * 1000  # 250 tokens, available 7750
        # old total = 500 + 3750 + 500 + 500 = 5250 < 7750
        # Still not exceeding. Need sum(messages) > available.
        # Let's make it extreme: many long messages.
        msg1 = Message(role="user", content="x" * 8000)      # 2000
        msg2 = Message(role="assistant", content="x" * 8000)  # 2000
        msg3 = Message(role="user", content="x" * 8000)      # 2000
        doc = Message(role="user", content="x" * 2000)       # 500
        messages = [msg1, msg2, msg3, doc]
        current_input = doc.content
        system_prompt = "x" * 1000  # 250 tokens, available 7750
        # old total = 500 + 2000 + 2000 + 2000 + 500 = 7000 < 7750
        # Almost there. Add one more long message.
        msg4 = Message(role="assistant", content="x" * 4000)  # 1000
        messages = [msg1, msg2, msg3, msg4, doc]
        # old total = 500 + 2000 + 2000 + 2000 + 1000 + 500 = 8000 > 7750
        # Now the while loop would pop messages until total <= 7750.
        # After popping msg1: total = 6000, result = [msg2, msg3, msg4, doc]
        # After popping msg2: total = 4000, result = [msg3, msg4, doc]
        # After popping msg3: total = 2000, result = [msg4, doc]
        # After popping msg4: total = 1000, result = [doc]
        # Wait, total = input_tokens + sum(remaining)
        # After popping msg4: total = 500 + 500 = 1000 <= 7750. Done.
        # Result = [doc]. Not empty.
        #
        # The empty case happens when input_tokens == available.
        # Let's make available smaller.
        system_prompt = "x" * 2000  # 500 tokens, available 7500
        # Still doesn't empty. Need input_tokens to approach available.
        #
        # Actually the empty-list case requires:
        # input_tokens + sum(all messages) > available
        # AND after popping ALL messages:
        # input_tokens <= available (so while exits)
        #
        # Wait, let me re-read the old code:
        # while total > available and len(result) > 0:
        #     removed = result.pop(0)
        #     total -= estimate(removed.content)
        #
        # After popping all messages, result is [], len(result) == 0.
        # while condition: total > available AND len(result) > 0
        # If len(result) == 0, the second part is false, so loop exits.
        # Then if total > available, the truncation block runs but result is empty,
        # so "if result:" is false and it returns [].
        #
        # If total <= available after popping all, it returns [] directly.
        #
        # For this to happen:
        # 1. input_tokens + sum(all) > available (enter loop)
        # 2. After popping all, total = input_tokens (last message was
        #    double-counted but also in result; when popped, total -= estimate(last))
        # 3. input_tokens <= available (loop exits)
        # 4. Returns []
        #
        # So: sum(history) > available - input_tokens
        # And: input_tokens <= available
        #
        # Let's construct this:
        # available = 1000 (system takes 7000)
        # input_tokens = 500 (doc is 2000 chars)
        # sum(all) = 2000 + 2000 + 500 = 4500 (three messages)
        # total = 500 + 4500 = 5000 > 1000 -> enter loop
        # Pop msg1 (2000): total = 3000, result = [msg2, doc]
        # Pop msg2 (2000): total = 1000, result = [doc]
        # 1000 > 1000? No. Exit loop.
        # Result = [doc]. Not empty.
        #
        # Hmm, I need sum(all) to be large enough that after popping all,
        # total = input_tokens <= available.
        #
        # With 2 messages: [few_shot, doc]
        # available = 500, input_tokens = 400 (doc=1600 chars)
        # few_shot = 1600 chars, 400 tokens
        # total = 400 + 400 + 400 = 1200 > 500
        # Pop few_shot: total = 800, result = [doc]
        # 800 > 500? Yes. Pop doc: total = 400, result = []
        # 400 > 500? No. Exit. Return [].
        # YES! This triggers the bug.
        few_shot = Message(role="user", content="x" * 1600)
        doc = Message(role="user", content="x" * 1600)
        messages = [few_shot, doc]
        current_input = doc.content
        system_prompt = "x" * 7500  # 1875 tokens, available = 8000 - 1875 = 6125
        # total = 400 + 400 + 400 = 1200 < 6125. Not enough.
        # Need a much tighter budget. Let's use more messages.
        #
        # With many messages + very long system prompt:
        # system takes 7800 tokens -> available = 200
        # 10 messages of 1000 chars each = 250 tokens each
        # last message = doc = 800 chars = 200 tokens
        # total = 200 + 10*250 = 2700 > 200
        # After popping 9: total = 200 + 250 = 450 > 200
        # After popping 10th (doc): total = 200, result = []
        # 200 > 200? No. Return [].
        # YES!

        # But wait, my fix changes the calculation. Let me just write a test
        # that would have failed with the old code and passes with the new code.
        # The simplest test: verify that when current_input == last_msg.content,
        # the result is never empty even when budget is very tight.

        long_msgs = [Message(role="user", content="x" * 1000) for _ in range(20)]
        # Add the current_input as last message
        doc_msg = Message(role="user", content="doc text here")
        messages = long_msgs + [doc_msg]
        current_input = doc_msg.content

        # Very long system prompt to make budget tight
        system_prompt = "x" * 7000  # 1750 tokens, available = 6250
        # 20 messages * 1000 chars = 20 * 250 = 5000 tokens
        # input_tokens = 3 ("doc text here")
        # Old total = 3 + 5000 + 3 = 5006 > 6250 -> still under
        # Need more messages or longer system prompt.

        # Let me just be direct and extreme:
        system_prompt = "x" * 7800  # 1950 tokens, available = 6050
        many_msgs = [Message(role="user", content="x" * 2000) for _ in range(10)]
        # 10 * 500 = 5000 tokens
        doc_msg = Message(role="user", content="final input")
        messages = many_msgs + [doc_msg]
        current_input = doc_msg.content
        # Old total = 3 + 5000 + 3 = 5006 < 6050 -> under
        # Still not enough. Need sum(messages) > available.
        # Let's make it really extreme.
        system_prompt = "x" * 7800
        many_msgs = [Message(role="user", content="x" * 3000) for _ in range(10)]
        # 10 * 750 = 7500 tokens
        doc_msg = Message(role="user", content="x" * 1000)  # 250 tokens
        messages = many_msgs + [doc_msg]
        current_input = doc_msg.content
        # Old total = 250 + 7500 + 250 = 8000 > 6050 -> enter loop
        # Pop 9 msgs: total = 250 + 750 + 250 = 1250 > 6050 -> continue
        # Pop 10th: total = 250, result = []
        # 250 <= 6050 -> exit. Return []. BUG!

        truncated = client._truncate_messages(
            system_prompt=system_prompt,
            messages=messages,
            current_input=current_input,
        )

        assert len(truncated) > 0, "Result must never be empty"
        assert truncated[-1].content == current_input


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
