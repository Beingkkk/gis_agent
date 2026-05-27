"""LLM interaction module.

Public API:
    LLMClient — Anthropic SDK wrapper with retry logic
    PromptBuilder — System prompt assembly
    classify_intent — Map user input to template
    extract_params — Extract template parameters from user input
    answer_question — RAG-enhanced document Q&A
    Message, IntentResult, ParamResult — Data models
    LLMError, LLMConnectionError, LLMRateLimitError, LLMContextError,
    LLMAuthError, LLMResponseError — Exceptions

Design: plan-llm v1.0.0 (DC-0030 ~ DC-0035)
"""

from llm.client import LLMClient
from llm.exceptions import (
    LLMAuthError,
    LLMConnectionError,
    LLMContextError,
    LLMError,
    LLMRateLimitError,
    LLMResponseError,
)
from llm.intent import classify_intent
from llm.models import IntentResult, Message, ParamResult
from llm.params import extract_params
from llm.prompts import PromptBuilder
from llm.qa import answer_question

__all__ = [
    "LLMClient",
    "PromptBuilder",
    "classify_intent",
    "extract_params",
    "answer_question",
    "Message",
    "IntentResult",
    "ParamResult",
    "LLMError",
    "LLMConnectionError",
    "LLMRateLimitError",
    "LLMContextError",
    "LLMAuthError",
    "LLMResponseError",
]
