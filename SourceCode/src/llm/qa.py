"""Template-knowledge-based Q&A.

Answers user questions using template metadata (concepts, notes,
common_errors) for usage guidance, or LLM parametric knowledge for
basic concepts.

When a template is locked (user has selected one), Q&A is scoped to
that template's full knowledge including param definitions and current
values, enabling contextual help like "how do I fill these params?"

Design: F1, P4, ADR-0001
"""

import logging
from typing import Callable, Dict, List, Optional

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


def _format_locked_template_context(
    template: TemplateDef,
    current_params: Optional[Dict[str, str]] = None,
) -> str:
    """Format a locked template with full param info for contextual Q&A.

    When a user asks "how do I fill these params?" while a template is
    locked, the LLM needs param definitions, defaults, options, and
    current values to give a precise, contextual answer.

    Args:
        template: The locked template (full TemplateDef with params).
        current_params: Currently filled parameter values, if any.

    Returns:
        Formatted context string.
    """
    lines: list[str] = [
        f"【当前已选模板】{template.name}（{template.id}）",
        f"描述：{template.description}",
    ]

    # Param definitions
    if template.params:
        lines.append("参数定义：")
        for p in template.params:
            parts: list[str] = [
                f"  - {p.name}（{p.type}）",
            ]
            if p.required:
                parts.append("[必填]")
            else:
                parts.append("[可选]")
            parts.append(f"：{p.description}")
            if p.default:
                parts.append(f"（默认值：{p.default}）")
            if p.options:
                parts.append(f"（可选值：{', '.join(p.options)}）")
            if p.must_exist:
                parts.append("（该文件必须已存在）")
            lines.append("".join(parts))

    # Current values
    if current_params:
        lines.append("当前已填写的参数值：")
        for name, value in current_params.items():
            lines.append(f"  - {name} = {value or '(未填写)'}")
        # Also note which params are not yet filled
        missing = [p.name for p in template.params if p.name not in current_params]
        if missing:
            lines.append(f"尚未填写的参数：{', '.join(missing)}")

    # Concepts
    if template.concepts:
        lines.append("相关概念：")
        for term, expl in template.concepts:
            lines.append(f"  - {term}：{expl}")

    # Notes
    if template.notes:
        lines.append("注意事项：")
        for note in template.notes:
            lines.append(f"  - {note}")

    # Common errors
    if template.common_errors:
        lines.append("常见错误：")
        for err_text, fix in template.common_errors:
            lines.append(f"  - {err_text}：{fix}")

    return "\n".join(lines)


def answer_question(
    user_input: str,
    templates: List[TemplateDef],
    history: List[Message],
    client: LLMClient,
    builder: PromptBuilder,
    on_chunk: Optional[Callable[[str], None]] = None,
    locked_template: Optional[TemplateDef] = None,
    current_params: Optional[Dict[str, str]] = None,
) -> str:
    """Generate answer based on template metadata or LLM parametric knowledge.

    **Code-level branching** (not prompt-level):
    - When *locked_template* is provided → template-knowledge Q&A with full
      param definitions and current values as context.
    - When *locked_template* is None → GIS-expert Q&A with NO template
      context; LLM answers from its own parametric knowledge.

    When *on_chunk* is provided, the response is streamed chunk-by-chunk
    via the callback while the full text is accumulated and returned.
    When *on_chunk* is None, the standard blocking API is used.

    Args:
        user_input: User question.
        templates: Matched templates (only used when locked_template is set,
            as supplementary context).
        history: Conversation history.
        client: LLM client.
        builder: Prompt builder.
        on_chunk: Optional callback invoked for each text chunk.
        locked_template: The currently locked template, if any.
        current_params: Currently filled parameter values, if any.

    Returns:
        Natural language answer (full text).

    Design:
        F1, P4, ADR-0001, DC-0069
    """
    # Code-level branch: template-knowledge vs GIS-expert
    if locked_template is not None:
        parts: list[str] = [
            _format_locked_template_context(locked_template, current_params)
        ]
        supplementary = [t for t in templates if t.id != locked_template.id][:3]
        if supplementary:
            parts.append("【相关模板参考】")
            parts.append(_format_template_context(supplementary))
        template_context = "\n\n".join(parts)
    else:
        template_context = None  # No template context → GIS-expert mode

    # Select prompt by scenario — LLM never guesses the intent
    if template_context is not None:
        system_prompt = builder.build_template_qa_prompt(template_context)
    else:
        system_prompt = builder.build_gis_expert_prompt()

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
