"""LLM client wrapper around anthropic SDK.

Design: DC-0030, DC-0031, DC-0033, DC-0034, ADR-0005
"""

import json
import logging
from collections.abc import Iterator
from typing import List

import anthropic
from tenacity import (
    RetryCallState,
    RetryError,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from config import get_config
from llm.exceptions import (
    LLMAuthError,
    LLMConnectionError,
    LLMContextError,
    LLMRateLimitError,
    LLMResponseError,
)
from llm.models import Message

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Retry policy helpers (ADR-0005)
# ---------------------------------------------------------------------------


def _should_retry(exc: BaseException) -> bool:
    """Return True if the exception is transient and should be retried."""
    if isinstance(
        exc,
        (
            anthropic.APIConnectionError,
            anthropic.APITimeoutError,
            anthropic.RateLimitError,
        ),
    ):
        return True
    if isinstance(exc, anthropic.APIStatusError):
        status = getattr(exc, "status_code", 0)
        return status == 429 or status >= 500
    return False


def _log_retry_attempt(retry_state: RetryCallState) -> None:
    """Log retry attempts in a format compatible with the original loop."""
    outcome = retry_state.outcome
    exc = outcome.exception() if outcome is not None else None
    attempt = retry_state.attempt_number

    if isinstance(exc, anthropic.APIConnectionError):
        logger.warning("LLM connection error (attempt %d/4): %s", attempt, exc)
    elif isinstance(exc, anthropic.APITimeoutError):
        logger.warning("LLM timeout (attempt %d/4): %s", attempt, exc)
    elif isinstance(exc, anthropic.RateLimitError):
        logger.warning("LLM rate limit (attempt %d/4): %s", attempt, exc)
    elif isinstance(exc, anthropic.APIStatusError):
        status = getattr(exc, "status_code", 0)
        if status == 429:
            logger.warning("LLM rate limit 429 (attempt %d/4)", attempt)
        elif status >= 500:
            logger.warning(
                "LLM server error %d (attempt %d/4)", status, attempt
            )


class LLMClient:
    """LLM client encapsulating anthropic SDK.

    Process-level singleton accessed via constructor.

    Design:
        DC-0030, DC-0031, DC-0034, ADR-0005
    """

    MAX_RETRIES: int = 3
    TOKEN_LIMIT: int = 8000
    SYSTEM_PROMPT_RESERVE: int = 2000
    MAX_INPUT_TOKENS: int = 2000

    def __init__(self) -> None:
        """Initialize anthropic client from Config.

        Raises:
            RuntimeError: Config not loaded.
        """
        cfg = get_config()
        self._anthropic = anthropic.Anthropic(
            base_url=cfg.llm.base_url,
            api_key=cfg.llm.auth_key,
        )
        self._model_name = cfg.llm.model_name

    def chat(
        self,
        system_prompt: str,
        messages: List[Message],
        temperature: float = 0.1,
        current_input: str = "",
    ) -> str:
        """Send chat request and return model-generated text.

        Args:
            system_prompt: System prompt.
            messages: History messages (excluding current turn).
            temperature: Sampling temperature.
            current_input: Current user input (for truncation). If empty,
                the last message in `messages` is treated as current input.

        Returns:
            Model-generated text content.

        Raises:
            LLMConnectionError: Network error, retries exhausted.
            LLMRateLimitError: Rate limit, retries exhausted.
            LLMContextError: Context length exceeded.
            LLMAuthError: Authentication error (401/403).

        Design:
            DC-0033, DC-0034, ADR-0005
        """
        # Determine current input: if explicit, pop last message
        api_messages = list(messages)
        if current_input:
            api_input = current_input
        elif api_messages:
            api_input = api_messages[-1].content
        else:
            api_input = ""

        # Truncate to fit token budget
        truncated = self._truncate_messages(system_prompt, api_messages, api_input)

        # Build API message list
        api_msg_list = [{"role": m.role, "content": m.content} for m in truncated]

        # Call API with tenacity-managed retries for transient failures
        try:
            return self._chat_with_retry(system_prompt, api_msg_list, temperature)
        except RetryError as exc:
            last_error = exc.last_attempt.exception()
            if isinstance(last_error, anthropic.RateLimitError):
                raise LLMRateLimitError(
                    f"Rate limit after {self.MAX_RETRIES} retries: {last_error}"
                ) from last_error
            raise LLMConnectionError(
                f"Connection failed after {self.MAX_RETRIES} retries: {last_error}"
            ) from last_error

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception(_should_retry),
        before_sleep=_log_retry_attempt,
    )
    def _chat_with_retry(
        self,
        system_prompt: str,
        api_messages: List[dict[str, str]],
        temperature: float,
    ) -> str:
        """Single API call wrapped with retry policy.

        Non-transient 4xx errors are converted to domain exceptions immediately
        and are not retried.
        """
        try:
            return self._call_api(system_prompt, api_messages, temperature)
        except anthropic.APIStatusError as exc:
            status = getattr(exc, "status_code", 0)
            if status == 429 or status >= 500:
                # Let tenacity handle retries for these status codes
                raise
            if status in (401, 403):
                logger.error("LLM authentication failed: %s", exc)
                raise LLMAuthError(f"Authentication failed: {exc}") from exc
            if status == 400:
                body = getattr(exc, "body", None) or {}
                if isinstance(body, dict):
                    err_msg = json.dumps(body)
                else:
                    err_msg = str(body)
                if "context" in err_msg.lower() or "length" in err_msg.lower():
                    logger.error("LLM context length exceeded: %s", exc)
                    raise LLMContextError(
                        f"Context length exceeded: {exc}"
                    ) from exc
                logger.error("LLM bad request: %s", exc)
                raise LLMResponseError(f"Bad request: {exc}") from exc
            logger.error("LLM API error %d: %s", status, exc)
            raise LLMResponseError(f"API error {status}: {exc}") from exc
        except anthropic.AuthenticationError as exc:
            logger.error("LLM authentication error: %s", exc)
            raise LLMAuthError(f"Authentication failed: {exc}") from exc
        except anthropic.PermissionDeniedError as exc:
            logger.error("LLM permission denied: %s", exc)
            raise LLMAuthError(f"Permission denied: {exc}") from exc

    def _truncate_messages(
        self,
        system_prompt: str,
        messages: List[Message],
        current_input: str,
    ) -> List[Message]:
        """Truncate messages to fit within token budget.

        Strategy:
        1. Reserve tokens for system prompt
        2. Keep current input (truncate if too long)
        3. Remove oldest history messages first
        4. If all history removed and still over budget,
           truncate current input

        Callers pass ``current_input`` derived from the last message, but
        ``messages`` still contains that last message.  We separate history
        from the current turn to avoid double-counting the last message.

        Design:
            DC-0033
        """
        sys_tokens = self._estimate_tokens(system_prompt)
        input_tokens = self._estimate_tokens(current_input)

        available = self.TOKEN_LIMIT - sys_tokens

        # If current input alone exceeds budget after system prompt
        if input_tokens > available:
            max_input_chars = available * 4
            if max_input_chars <= 0:
                raise LLMContextError(
                    f"System prompt too long ({sys_tokens} tokens). "
                    "Cannot fit any input."
                )
            truncated_input = current_input[:max_input_chars]
            return [Message(role="user", content=truncated_input)]

        # Separate history from current input to avoid double-counting.
        # current_input is typically messages[-1].content.
        if messages and messages[-1].content == current_input:
            history = list(messages[:-1])
        else:
            history = list(messages)

        total = input_tokens + sum(
            self._estimate_tokens(m.content) for m in history
        )

        # Remove oldest history messages until under budget
        while total > available and len(history) > 0:
            removed = history.pop(0)
            total -= self._estimate_tokens(removed.content)

        # If still over budget, truncate current input
        if total > available:
            remaining = available - sum(
                self._estimate_tokens(m.content) for m in history
            )
            max_chars = max(0, remaining * 4)
            truncated_input = current_input[:max_chars]
            return history + [Message(role="user", content=truncated_input)]

        # Reconstruct: history + current input
        return history + [Message(role="user", content=current_input)]

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough token estimate: len(text) // 4.

        This is a fast heuristic. Actual token counts vary by model
        and tokenizer, but this is sufficient for budget management.
        """
        return max(1, len(text) // 4)

    def _call_api(
        self,
        system_prompt: str,
        messages: List[dict[str, str]],
        temperature: float,
    ) -> str:
        """Single API call without retry.

        Args:
            system_prompt: System prompt text.
            messages: List of {"role": str, "content": str}.
            temperature: Sampling temperature.

        Returns:
            Model response text.
        """
        response = self._anthropic.messages.create(
            model=self._model_name,
            system=system_prompt,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=4096,
        )
        # response.content may contain ThinkingBlock (type="thinking")
        # in addition to TextBlock. Find the first text block.
        for block in response.content:
            if getattr(block, "type", None) == "text":
                return block.text  # type: ignore[union-attr]
        raise LLMResponseError("No text content in LLM response")

    def chat_stream(
        self,
        system_prompt: str,
        messages: List[Message],
        temperature: float = 0.1,
        current_input: str = "",
    ) -> Iterator[str]:
        """Stream LLM response as text chunks.

        Uses Anthropic SDK's streaming API. No retry logic —
        failures are raised immediately since retries are awkward
        mid-stream.

        Args:
            system_prompt: System prompt.
            messages: History messages.
            temperature: Sampling temperature.
            current_input: Current user input (for truncation).

        Yields:
            Text chunks as the model generates them.

        Design:
            DC-0068
        """
        api_messages = list(messages)
        if current_input:
            api_input = current_input
        elif api_messages:
            api_input = api_messages[-1].content
        else:
            api_input = ""

        truncated = self._truncate_messages(
            system_prompt, api_messages, api_input
        )
        api_msg_list = [
            {"role": m.role, "content": m.content} for m in truncated
        ]

        # Anthropic SDK 0.104.1: messages.create(stream=True) returns
        # Stream[RawMessageStreamEvent], not MessageStream. Iterate directly
        # and extract text from content_block_delta events.
        with self._anthropic.messages.create(  # type: ignore[union-attr]
            model=self._model_name,
            system=system_prompt,
            messages=api_msg_list,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=4096,
            stream=True,
        ) as stream:
            for event in stream:
                if event.type == "content_block_delta":
                    delta = event.delta  # type: ignore[union-attr]
                    if hasattr(delta, "text"):
                        yield delta.text
