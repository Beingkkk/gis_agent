"""Diagnosis context builder for error recovery.

Provides a shared helper to build the context string used by LLM
error diagnosis. Eliminates duplication between the API layer
(session.py) and the deprecated CLI layer (processor.py).

Design: plan-core DC-0049
"""

import logging
from typing import TYPE_CHECKING

from core.models import Session

if TYPE_CHECKING:
    from templates.engine import TemplateEngine

logger = logging.getLogger(__name__)


def build_diagnosis_context(session: Session, engine: "TemplateEngine") -> str:
    """Build diagnosis context string for LLM error analysis.

    Includes template info, param definitions, current values,
    and rendered script content.

    Args:
        session: Current Session with template and params.
        engine: TemplateEngine for rendering the script.

    Returns:
        Context string for analyze_execution_error().
    """
    template = session.template
    if template is None:
        return "模板信息不可用。"

    param_lines: list[str] = []
    for p in template.params:
        tag = "必填" if p.required else "可选"
        if p.default is not None:
            tag += f"，默认 {p.default}"
        param_lines.append(f"  • {p.name}（{tag}，类型 {p.type}）：{p.description}")

    current_lines: list[str] = []
    for name, value in session.params.items():
        current_lines.append(f"    {name} = {value}")

    try:
        rendered = engine.render(template, session.params)
        script_content = rendered.content.strip()
    except Exception:
        script_content = "（脚本渲染失败）"

    return (
        f"【模板信息】\n"
        f"名称：{template.name}\n"
        f"描述：{template.description}\n\n"
        f"【参数定义】\n"
        + "\n".join(param_lines)
        + "\n\n"
        + "【当前参数值】\n"
        + "\n".join(current_lines)
        + "\n\n"
        + "【渲染后脚本】\n"
        + script_content
        + "\n"
    )
