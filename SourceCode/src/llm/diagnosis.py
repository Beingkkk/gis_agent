"""Execution error diagnosis.

LLM-driven analysis of GDAL script execution failures.

Design: DC-0036
"""

import json
import logging
import re
from typing import Any, Dict, List

from llm.client import LLMClient
from llm.models import ErrorDiagnosis, Message
from llm.prompts import PromptBuilder

logger = logging.getLogger(__name__)


def analyze_execution_error(
    returncode: int,
    stdout: str,
    stderr: str,
    diagnosis_context: str,
    history: List[Message],
    client: LLMClient,
    builder: PromptBuilder,
) -> ErrorDiagnosis:
    """Analyze GDAL script execution error, return structured diagnosis.

    Args:
        returncode: Process exit code.
        stdout: Process stdout.
        stderr: Process stderr.
        diagnosis_context: Full context string built by caller, containing
            template info, param schema, current params, rendered script.
        history: Conversation history.
        client: LLM client.
        builder: Prompt builder.

    Returns:
        ErrorDiagnosis with cause, suggestion, fixed_params, confidence,
        and can_auto_fix flag.

    Design:
        DC-0036
    """
    task_context = (
        "【错误诊断任务】\n"
        "你是一名 GDAL 命令行工具的错误诊断专家。\n"
        "分析以下执行错误，结合模板和参数上下文，判断错误根因并给出修复建议。"
    )
    system_prompt = builder.build_system_prompt(task_context=task_context)

    user_prompt = (
        f"{diagnosis_context}\n\n"
        f"【执行结果】\n"
        f"返回码：{returncode}\n"
        f"标准输出：\n{stdout or '(无)'}\n\n"
        f"错误输出：\n{stderr or '(无)'}\n\n"
        f"请分析错误根因，输出严格 JSON（不要 Markdown 代码块）：\n"
        f"{{\n"
        f'  "cause": "错误根因，用中文简洁描述",\n'
        f'  "suggestion": "修复建议，用中文描述",\n'
        f'  "fixed_params": {{"参数名": "修正后的值"}},\n'
        f'  "confidence": 0.0到1.0,\n'
        f'  "can_auto_fix": true或false\n'
        f"}}\n\n"
        f"can_auto_fix 判定规则：\n"
        f"- true：仅涉及参数值修改（如路径、坐标系、格式）即可修复\n"
        f"- false：需要用户手动解决系统级问题（如权限、GDAL版本、数据损坏）\n"
        f"confidence < 0.5 时，can_auto_fix 必须设为 false。"
    )

    messages = list(history)
    messages.append(Message(role="user", content=user_prompt))

    try:
        response = client.chat(
            system_prompt=system_prompt,
            messages=messages,
            temperature=0.1,
        )
    except Exception as exc:
        logger.error("LLM diagnosis failed: %s", exc)
        return _fallback_diagnosis()

    return _parse_diagnosis_response(response)


def _parse_diagnosis_response(response: str) -> ErrorDiagnosis:
    """Parse LLM diagnosis response into ErrorDiagnosis.

    Handles markdown code block stripping and JSON parsing.
    Falls back to conservative diagnosis on any failure.
    """
    _cleaned = re.sub(
        r"^```(?:json)?\s*|\s*```$", "", response.strip(), flags=re.MULTILINE
    )
    try:
        parsed = json.loads(_cleaned)
    except json.JSONDecodeError:
        logger.error("Failed to parse diagnosis response as JSON: %s", response)
        return _fallback_diagnosis()

    required_fields = (
        "cause",
        "suggestion",
        "fixed_params",
        "confidence",
        "can_auto_fix",
    )
    for field in required_fields:
        if field not in parsed:
            logger.error(
                "Missing field '%s' in diagnosis response: %s", field, response
            )
            return _fallback_diagnosis()

    cause = str(parsed["cause"])
    suggestion = str(parsed["suggestion"])
    fixed_params = _filter_fixed_params(parsed.get("fixed_params", {}))
    confidence = float(parsed["confidence"])
    can_auto_fix = bool(parsed["can_auto_fix"])

    # Enforce low-confidence rule
    if confidence < 0.5:
        can_auto_fix = False

    return ErrorDiagnosis(
        cause=cause,
        suggestion=suggestion,
        fixed_params=fixed_params,
        confidence=confidence,
        can_auto_fix=can_auto_fix,
    )


def _filter_fixed_params(raw: dict[str, Any]) -> dict[str, str]:
    """Filter fixed_params to only string keys and string values.

    Non-string keys/values are converted to string or dropped.
    """
    result: Dict[str, str] = {}
    for key, value in raw.items():
        if isinstance(key, str) and isinstance(value, str):
            result[key] = value
        elif isinstance(key, str):
            result[key] = str(value)
    return result


def _fallback_diagnosis() -> ErrorDiagnosis:
    """Return a conservative diagnosis when LLM fails.

    Design:
        DC-0036 fallback strategy
    """
    return ErrorDiagnosis(
        cause="诊断失败，无法自动分析错误原因。",
        suggestion="请检查上方错误输出，或尝试手动修改参数后重试。",
        fixed_params={},
        confidence=0.0,
        can_auto_fix=False,
    )
