"""Prompt builder and system prompt constants.

Design: DC-0032, DC-0035, ADR-0001
"""

from typing import Optional

# Fixed safety constraints — never truncated
_FIXED_CONSTRAINTS = """你是 GIS Agent，一个专业的地理信息系统数据处理助手。

【核心规则】
1. 你只能从预定义的模板中选择，绝不直接生成 GDAL 命令字符串。
2. 所有脚本必须在执行前向用户展示完整内容，获得明确确认（Y/N）后方可执行。
3. 用法指导类知识仅来源于提供的模板元数据，禁止编造模板中未定义的参数或命令。
4. 基础概念类问题可使用你的参数知识回答。
5. 禁止执行任何未经用户确认的脚本或文件操作。

【命令生成规则】
- 你仅负责：识别用户意图 → 选择对应模板 → 提取参数
- 实际 GDAL 命令由 Jinja2 模板渲染生成，不是你自由编写
- 如果用户请求没有匹配的模板，如实告知，不提供猜测性命令

【问答规则】
- 若提供了模板元数据：仅基于该元数据回答用法问题，不扩展未提及的参数
- 若未提供模板元数据（基础概念问题）：使用你的参数知识回答
- 用户连续提问时，如果新问题与之前的问题明显是不同主题（如问完"shp是什么"又问"tif是什么"），只回答新问题，不要重复之前的内容；如果是对之前问题的追问或延伸（如问完"shp是什么"又问"shp能转成什么"），自然地承接上文
"""


def _format_template_context(template_context: str) -> str:
    """Format template knowledge context section."""
    return f"""
【模板知识上下文】
以下是与用户问题相关的模板元数据，请仅基于这些信息回答用法指导类问题：
{template_context}
"""


def _format_task_context(task_context: str) -> str:
    """Format task context section."""
    return f"""
【当前任务状态】
{task_context}
"""


def _format_agents_md(agents_md: str) -> str:
    """Format Agents.md section."""
    return f"""
【项目配置 (Agents.md)】
{agents_md}
"""


class PromptBuilder:
    """System prompt builder.

    Assembles fixed constraints, Agents.md, and template knowledge context.

    Design:
        DC-0032, DC-0035, ADR-0001
    """

    def __init__(self, agents_md: Optional[str] = None) -> None:
        """Args:
        agents_md: Full text of workspace Agents.md, or None.
        """
        self._agents_md = agents_md

    def build_system_prompt(
        self,
        template_context: Optional[str] = None,
        task_context: Optional[str] = None,
    ) -> str:
        """Assemble system prompt.

        Args:
            template_context: Template metadata context (Q&A scene).
            task_context: Current task state description (param extraction).

        Returns:
            Complete system prompt string.
        """
        parts: list[str] = [_FIXED_CONSTRAINTS]

        if self._agents_md is not None:
            parts.append(_format_agents_md(self._agents_md))

        if template_context is not None and template_context.strip():
            parts.append(_format_template_context(template_context))

        if task_context is not None:
            parts.append(_format_task_context(task_context))

        return "\n".join(parts)
