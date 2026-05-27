"""LLM module exceptions.

Design: DC-0030, DC-0034
"""


class LLMError(Exception):
    """Base exception for LLM module."""


class LLMConnectionError(LLMError):
    """Network connection error (timeout, DNS failure, etc.)."""


class LLMRateLimitError(LLMError):
    """API rate limit exceeded (429)."""


class LLMContextError(LLMError):
    """Context length exceeds model limit."""


class LLMAuthError(LLMError):
    """Authentication failure (401/403)."""


class LLMResponseError(LLMError):
    """Response parsing failure (unexpected format)."""
