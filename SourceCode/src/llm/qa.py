"""Template-knowledge-based Q&A.

Answers user questions using template metadata (concepts, notes,
common_errors) for usage guidance, or LLM parametric knowledge for
basic concepts.

Design: F1, P4, ADR-0001
"""

import logging
from typing import Callable, List, Optional

from core.models import TemplateDef
from llm.client import LLMClient
from llm.models import Message
from llm.prompts import PromptBuilder

logger = logging.getLogger(__name__)


def _format_template_context(templates: List[TemplateDef]) -> str:
    """Format template metadata into context string for LLM.

    Args:
        templates: Matched templates with knowledge metadata.

    Returns:
        Formatted context string.
    """
    if not templates:
        return ""

    parts: list[str] = []
    for i, t in enumerate(templates, 1):
        lines: list[str] = [f"【模板 {i}】{t.name}（{t.id}）"]
        if t.description:
            lines.append(f"描述：{t.description}")
        if t.concepts:
            for term, expl in t.concepts:
                lines.append(f"概念「{term}」：{expl}")
        if t.notes:
            for note in t.notes:
                lines.append(f"提示：{note}")
        if t.common_errors:
            for err_text, fix in t.common_errors:
                lines.append(f"常见错误「{err_text}」：{fix}")
        parts.append("\n".join(lines))

    return "\n\n".join(parts)


def answer_question(
    user_input: str,
    templates: List[TemplateDef],
    history: List[Message],
    client: LLMClient,
    builder: PromptBuilder,
    on_chunk: Optional[Callable[[str], None]] = None,
) -> str:
    """Generate answer based on template metadata or LLM parametric knowledge.

    When *on_chunk* is provided, the response is streamed chunk-by-chunk
    via the callback while the full text is accumulated and returned.
    When *on_chunk* is None, the standard blocking API is used.

    Args:
        user_input: User question.
        templates: Matched templates with knowledge metadata.
        history: Conversation history.
        client: LLM client.
        builder: Prompt builder.
        on_chunk: Optional callback invoked for each text chunk.

    Returns:
        Natural language answer (full text).

    Design:
        F1, P4, ADR-0001, DC-0069
    """
    template_context = _format_template_context(templates)
    system_prompt = builder.build_system_prompt(template_context=template_context)

    messages = list(history)
    messages.append(Message(role="user", content=user_input))

    if on_chunk is not None:
        chunks: list[str] = []
        for chunk in client.chat_stream(
            system_prompt=system_prompt,
            messages=messages,
            temperature=0.3,
        ):
            on_chunk(chunk)
            chunks.append(chunk)
        return "".join(chunks)

    response = client.chat(
        system_prompt=system_prompt,
        messages=messages,
        temperature=0.3,
    )
    return response
