"""LLM interaction module.

Public API:
    LLMClient — Anthropic SDK wrapper with retry logic
    PromptBuilder — System prompt assembly
    classify_intent — Map user input to template
    extract_params — Extract template parameters from user input
    analyze_execution_error — LLM-driven execution error diagnosis
    answer_question — RAG-enhanced document Q&A
    Message, IntentResult, ParamResult, TemplateInfo, ErrorDiagnosis — Data models
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
from llm.diagnosis import analyze_execution_error
from llm.intent import classify_intent
from llm.keywords import extract_keywords
from llm.models import ErrorDiagnosis, IntentResult, Message, ParamResult, TemplateInfo
from llm.params import extract_params
from llm.prompts import PromptBuilder
from llm.qa import answer_question

__all__ = [
    "LLMClient",
    "PromptBuilder",
    "classify_intent",
    "extract_params",
    "extract_keywords",
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
