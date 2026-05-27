"""Parameter extraction.

Design: F3
"""

import json
import logging
from typing import Any, Dict, List

from llm.client import LLMClient
from llm.exceptions import LLMResponseError
from llm.models import Message, ParamResult
from llm.prompts import PromptBuilder

logger = logging.getLogger(__name__)


def extract_params(
    user_input: str,
    template_id: str,
    param_schema: Dict[str, Any],
    current_params: Dict[str, str],
    history: List[Message],
    client: LLMClient,
    builder: PromptBuilder,
) -> ParamResult:
    """Extract template parameters from user input.

    Args:
        user_input: Current user input (may be answer to a previous question).
        template_id: Confirmed template ID.
        param_schema: Parameter schema (field names, types, required, descriptions).
        current_params: Already collected parameters.
        history: Conversation history.
        client: LLM client.
        builder: Prompt builder.

    Returns:
        Parameter extraction result with collected, missing, and questions.

    Design:
        F3
    """
    schema_json = json.dumps(param_schema, ensure_ascii=False, indent=2)
    current_json = json.dumps(current_params, ensure_ascii=False, indent=2)

    task_context = (
        f"当前模板: {template_id}\n"
        f"已收集参数: {current_json}\n"
        f"参数Schema: {schema_json}"
    )

    system_prompt = builder.build_system_prompt(task_context=task_context)

    user_prompt = (
        f"用户输入：{user_input}\n\n"
        f"请从用户输入中提取参数，并与已收集的参数合并。\n"
        f"对于缺失的必填参数，生成向用户追问的问题。\n\n"
        f"输出格式（严格 JSON，不要 Markdown 代码块）：\n"
        f'{{"params": {{"字段名": "值", ...}}, '
        f'"missing": ["缺失字段名", ...], '
        f'"questions": ["追问问题", ...]}}'
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
        logger.error("Failed to parse param response as JSON: %s", response)
        raise LLMResponseError(f"Param response is not valid JSON: {exc}") from exc

    # Validate required fields
    for key in ("params", "missing", "questions"):
        if key not in parsed:
            logger.error("Missing field '%s' in param response: %s", key, response)
            raise LLMResponseError(f"Param response missing required field: {key}")

    new_params: Dict[str, str] = dict(parsed["params"])

    # Merge with current_params (new values take precedence)
    merged = dict(current_params)
    merged.update(new_params)

    missing: List[str] = list(parsed["missing"])
    questions: List[str] = list(parsed["questions"])

    return ParamResult(
        params=merged,
        missing=missing,
        questions=questions,
    )
