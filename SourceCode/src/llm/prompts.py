"""Prompt builder and system prompt constants.

Design: DC-0032, DC-0035
"""

from typing import Optional

# Fixed safety constraints — never truncated
_FIXED_CONSTRAINTS = """你是 GIS Agent，一个专业的地理信息系统数据处理助手。

【核心规则】
1. 你只能从预定义的模板中选择，绝不直接生成 GDAL 命令字符串。
2. 所有脚本必须在执行前向用户展示完整内容，获得明确确认（Y/N）后方可执行。
3. 仅基于提供的 GDAL 官方文档内容回答问题；若文档中无相关信息，回答"文档中未提及"。
4. 禁止执行任何未经用户确认的脚本或文件操作。

【命令生成规则】
- 你仅负责：识别用户意图 → 选择对应模板 → 提取参数
- 实际 GDAL 命令由 Jinja2 模板渲染生成，不是你自由编写
- 如果用户请求没有匹配的模板，如实告知，不提供猜测性命令
"""


def _format_rag_context(rag_context: str) -> str:
    """Format RAG context section."""
    return f"""
【GDAL 文档上下文】
以下是从本地 GDAL 官方文档中检索到的相关片段，请仅基于这些片段回答：
{rag_context}
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

    Assembles fixed constraints, Agents.md, and RAG context.

    Design:
        DC-0032, DC-0035
    """

    def __init__(self, agents_md: Optional[str] = None) -> None:
        """Args:
        agents_md: Full text of workspace Agents.md, or None.
        """
        self._agents_md = agents_md

    def build_system_prompt(
        self,
        rag_context: Optional[str] = None,
        task_context: Optional[str] = None,
    ) -> str:
        """Assemble system prompt.

        Args:
            rag_context: RAG retrieved document fragments (Q&A scene).
            task_context: Current task state description (param extraction).

        Returns:
            Complete system prompt string.
        """
        parts: list[str] = [_FIXED_CONSTRAINTS]

        if self._agents_md is not None:
            parts.append(_format_agents_md(self._agents_md))

        if rag_context is not None:
            parts.append(_format_rag_context(rag_context))

        if task_context is not None:
            parts.append(_format_task_context(task_context))

        return "\n".join(parts)
