"""LLM interaction module.

Public API:
    LLMClient — Anthropic SDK wrapper with retry logic
    PromptBuilder — System prompt assembly
    classify_intent — Map user input to template
    extract_params — Extract template parameters from user input
    analyze_execution_error — LLM-driven execution error diagnosis
    answer_question — Template-knowledge-based Q&A
    Message, IntentResult, ParamResult, TemplateInfo, ErrorDiagnosis — Data models
    LLMError, LLMConnectionError, LLMRateLimitError, LLMContextError,
    LLMAuthError, LLMResponseError — Exceptions

Design: plan-llm v1.1.0 (DC-0030 ~ DC-0036), ADR-0001
"""

from llm.client import LLMClient
from llm.diagnosis import analyze_execution_error
from llm.exceptions import (
    LLMAuthError,
    LLMConnectionError,
    LLMContextError,
    LLMError,
    LLMRateLimitError,
    LLMResponseError,
)
from llm.intent import classify_intent
from llm.models import ErrorDiagnosis, IntentResult, Message, ParamResult, TemplateInfo
from llm.params import extract_params
from llm.prompts import PromptBuilder
from llm.qa import answer_question

__all__ = [
    "LLMClient",
    "PromptBuilder",
    "classify_intent",
    "extract_params",
    "analyze_execution_error",
    "answer_question",
    "Message",
    "IntentResult",
    "ParamResult",
    "TemplateInfo",
    "ErrorDiagnosis",
    "LLMError",
    "LLMConnectionError",
    "LLMRateLimitError",
    "LLMContextError",
    "LLMAuthError",
    "LLMResponseError",
]
