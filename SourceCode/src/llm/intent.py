"""Intent classification.

Design: F2, P1
"""

import json
import logging
from typing import List

from llm.client import LLMClient
from llm.exceptions import LLMResponseError
from llm.models import IntentResult, Message, TemplateInfo
from llm.prompts import PromptBuilder

logger = logging.getLogger(__name__)


def _format_templates(templates: List[TemplateInfo]) -> str:
    """Format template list for LLM prompt."""
    lines: List[str] = []
    for t in templates:
        line = f"- {t.id}: {t.name} — {t.description}"
        lines.append(line)
    return "\n".join(lines)


def classify_intent(
    user_input: str,
    available_templates: List[TemplateInfo],
    history: List[Message],
    client: LLMClient,
    builder: PromptBuilder,
) -> IntentResult:
    """Classify user input to predefined template.

    Args:
        user_input: Current user input.
        available_templates: Available template metadata (id, name, description).
        history: Conversation history.
        client: LLM client.
        builder: Prompt builder.

    Returns:
        Classification result with template ID and confidence.

    Design:
        F2, P1
    """
    templates_str = _format_templates(available_templates)
    template_ids = [t.id for t in available_templates]
    task_context = (
        f"【意图分类任务】\n"
        f"可用模板：\n{templates_str}\n"
        f"请仅从以上模板中选择（按ID），禁止选择列表之外的模板。"
    )
    system_prompt = builder.build_system_prompt(task_context=task_context)

    user_prompt = (
        f"用户输入：{user_input}\n\n"
        f"请分析用户意图，从可用模板中选择最匹配的一个。"
        f"如果用户意图与任何模板都不匹配，template_id 留空。\n\n"
        f"输出格式（严格 JSON，不要 Markdown 代码块）：\n"
        f'{{"template_id": "模板ID或空字符串", '
        f'"confidence": 0.0到1.0, '
        f'"reasoning": "分类理由"}}'
    )

    messages = list(history)
    messages.append(Message(role="user", content=user_prompt))

    response = client.chat(
        system_prompt=system_prompt,
        messages=messages,
        temperature=0.1,
    )

    try:
        parsed = json.loads(response)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse intent response as JSON: %s", response)
        raise LLMResponseError(f"Intent response is not valid JSON: {exc}") from exc

    for required_field in ("template_id", "confidence", "reasoning"):
        if required_field not in parsed:
            logger.error(
                "Missing field '%s' in intent response: %s",
                required_field,
                response,
            )
            raise LLMResponseError(
                f"Intent response missing required field: {required_field}"
            )

    template_id = parsed["template_id"]
    confidence = float(parsed["confidence"])
    reasoning = parsed["reasoning"]

    # Validate template_id is in available list
    if template_id and template_id not in template_ids:
        logger.warning(
            "LLM returned unknown template_id '%s', setting confidence=0",
            template_id,
        )
        return IntentResult(
            template_id="",
            confidence=0.0,
            reasoning=f"Invalid template '{template_id}' returned by model",
        )

    return IntentResult(
        template_id=template_id,
        confidence=confidence,
        reasoning=reasoning,
    )
