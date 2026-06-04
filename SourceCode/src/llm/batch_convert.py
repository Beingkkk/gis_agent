"""Batch script conversion using LLM.

Converts a single-file GDAL script into a directory-iterating batch script
by wrapping it in a for-loop. The core GDAL command is preserved verbatim;
only the hardcoded file paths are replaced with loop variables.

Design:
    plan-batch-convert v1.0.0 (DC-0113)
"""

import logging
from typing import Any

from llm.client import LLMClient
from llm.models import Message

logger = logging.getLogger(__name__)

BATCH_SYSTEM_PROMPT = """你是 GIS Agent 的批量脚本转换专家。

你的任务：将单文件 GDAL 命令改写为遍历目录执行的 Windows cmd 批量脚本。

【核心规则】
1. 识别所有 type=file_path 的输入参数，将其值中的文件路径改为目录路径，
   提取文件扩展名作为遍历模式。
2. 输出参数（type=file_path 且语义为输出）使用 {原始文件名} 变量替换
   输出文件名。
3. 核心 GDAL 命令必须一字不改地保留，只将硬编码路径替换为 for 循环变量。
4. 外层使用 Windows cmd 的 for %%f in (...) do (...) 循环。
5. 需要 setlocal enabledelayedexpansion 来使用 !变量! 语法。
6. 每个文件执行后检查 if errorlevel 1，失败则 echo 错误信息并 exit /b 1。
7. 如果命令没有输出文件参数（如 gdalinfo、ogrinfo 输出到 stdout），
   将输出重定向到文本文件。

【输出格式】
- 使用 Markdown 格式输出
- 先给出简短说明（1-2 句话）
- 然后用代码块给出完整脚本
- 如果不能转换，说明原因并给出建议"""


def build_batch_convert_prompt(
    script: str,
    template_name: str,
    params_meta: list[dict[str, Any]],
    params_values: dict[str, str],
) -> str:
    """Build user prompt for batch conversion.

    Args:
        script: Rendered single-file script.
        template_name: Template name for context.
        params_meta: Template parameter definitions
            (name, type, description, required, default).
        params_values: Actual user-provided parameter values.

    Returns:
        Formatted user prompt.
    """
    lines = [
        f"模板名称：{template_name}",
        "",
        "【参数定义】",
    ]
    for p in params_meta:
        req = "必填" if p.get("required") else "可选"
        default = f" (默认: {p['default']})" if p.get("default") else ""
        lines.append(
            f"- {p['name']} ({p['type']}, {req}): {p['description']}{default}"
        )

    lines.extend([
        "",
        "【用户填写的实际值】",
    ])
    for name, value in params_values.items():
        lines.append(f"- {name} = {value}")

    lines.extend([
        "",
        "【当前单文件脚本】",
        "```batch",
        script,
        "```",
        "",
        "请将其改写为遍历目录执行的批量脚本。",
    ])

    return "\n".join(lines)


def convert_to_batch_script(
    script: str,
    template_name: str,
    params_meta: list[dict[str, Any]],
    params_values: dict[str, str],
    client: LLMClient,
) -> str:
    """Convert single-file script to batch script using LLM.

    Args:
        script: Rendered single-file script.
        template_name: Template name.
        params_meta: Template parameter definitions.
        params_values: User-provided parameter values.
        client: LLM client instance.

    Returns:
        LLM response text (Markdown format).
    """
    user_prompt = build_batch_convert_prompt(
        script, template_name, params_meta, params_values
    )

    logger.info("Batch convert prompt length: %d chars", len(user_prompt))

    try:
        response = client.chat(
            system_prompt=BATCH_SYSTEM_PROMPT,
            messages=[Message(role="user", content=user_prompt)],
            temperature=0.2,
        )
        return response
    except Exception as exc:
        logger.error("Batch convert LLM call failed: %s", exc)
        return (
            f"批量转换失败：{exc}\n\n"
            "请稍后重试，或手动编写 for 循环脚本。"
        )
