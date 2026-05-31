"""Prompt builder and system prompt constants.

Design: DC-0032, DC-0035, ADR-0001
"""

from typing import Optional

# ── 1. 意图识别 Prompt ──────────────────────────────────────────────────────
# 用于 classify_intent：从候选模板中选择最匹配的一个
_INTENT_SYSTEM = """你是 GIS Agent 的意图识别模块。

你的唯一任务：从候选模板列表中选出最匹配用户请求的一个模板，并给出置信度。

【规则】
1. 只能从提供的候选模板中选择（按 template_id），禁止编造列表外的模板ID。
2. 即使不完全匹配，也返回最接近的模板，用 confidence 反映匹配程度。
3. 禁止直接生成 GDAL 命令字符串。
4. 输出严格 JSON，不要 Markdown 代码块。"""

# ── 2. 模板知识问答 Prompt ──────────────────────────────────────────────────
# 用于 answer_question（用户已锁定模板）：基于模板上下文回答用法问题
_TEMPLATE_QA_SYSTEM = """你是 GIS Agent 的模板问答助手。

你的任务：基于下方提供的模板上下文，回答用户关于该模板用法的问题。

【规则】
1. 所有回答必须基于提供的模板上下文。
2. 禁止编造模板中未定义的参数或命令。
3. 可结合模板内容给出具体示例和参数填写建议。
4. 对于基础概念类问题，可补充通用 GIS 知识作为背景说明。
5. 用户连续提问时，不同主题只答新问题；追问或延伸则承接上文。"""

# ── 3. GIS 专家问答 Prompt ──────────────────────────────────────────────────
# 用于 answer_question（无锁定模板）：纯 GIS 知识问答
_GIS_EXPERT_SYSTEM = """你是 GIS 领域的专家助手。

你的任务：使用你的参数知识回答用户的 GIS 相关问题。

【规则】
1. 可自由引用通用 GIS 知识、GDAL 工具用法、数据格式标准和最佳实践。
2. 禁止编造具体模板的参数或命令（因为你当前没有模板上下文）。
3. 提供准确、实用的技术建议。
4. 用户连续提问时，不同主题只答新问题；追问或延伸则承接上文。"""

# ── 4. 参数提取 Prompt ──────────────────────────────────────────────────────
# 用于 extract_params：从用户输入中提取参数值
_PARAM_SYSTEM = """你是 GIS Agent 的参数提取模块。

你的任务：从用户输入中提取模板参数值，识别缺失的必填参数并生成追问问题。

【规则】
1. 仅提取已定义的参数字段，不编造新参数。
2. 区分必填和可选参数——必填缺失时必须追问，可选缺失时可忽略。
3. 输出严格 JSON，不要 Markdown 代码块。"""

# ── 5. 错误诊断 Prompt ──────────────────────────────────────────────────────
# 用于 analyze_execution_error：分析执行错误
_DIAGNOSIS_SYSTEM = """你是 GDAL 命令行工具的错误诊断专家。

你的任务：分析 GDAL 脚本执行错误，结合模板和参数上下文，判断错误根因并给出修复建议。

【规则】
1. 结合提供的模板信息、参数值、渲染后的脚本和错误输出进行分析。
2. can_auto_fix 判定：
   - true：仅涉及参数值修改（如路径、坐标系、格式）即可修复。
   - false：需要用户手动解决系统级问题（如权限、GDAL 版本、数据损坏）。
3. confidence < 0.5 时，can_auto_fix 必须设为 false。
4. 输出严格 JSON，不要 Markdown 代码块。"""


def _format_template_context(template_context: str) -> str:
    """Format template knowledge context section."""
    return f"""
【模板知识上下文】
{template_context}
"""


def _format_task_context(task_context: str) -> str:
    """Format task context section."""
    return f"""
【当前任务上下文】
{task_context}
"""


class PromptBuilder:
    """System prompt builder for LLM calls.

    Provides scenario-specific system prompts so the LLM never has to
    guess the user's intent — the calling code selects the prompt.

    Design:
        DC-0032, DC-0035, ADR-0001
    """

    def __init__(self) -> None:
        """Initialize prompt builder."""

    def _assemble(self, base: str, extra: Optional[str] = None) -> str:
        """Assemble final prompt from base + optional extra."""
        parts: list[str] = [base]
        if extra is not None and extra.strip():
            parts.append(extra)
        return "\n".join(parts)

    # ── Scenario 1: Intent classification ─────────────────────────────────

    def build_intent_prompt(self, task_context: str) -> str:
        """Build system prompt for intent classification.

        Args:
            task_context: Candidate template list and selection rules.

        Returns:
            System prompt for classify_intent().
        """
        return self._assemble(
            _INTENT_SYSTEM,
            _format_task_context(task_context),
        )

    # ── Scenario 2: Template-knowledge Q&A ────────────────────────────────

    def build_template_qa_prompt(self, template_context: str) -> str:
        """Build system prompt for template-knowledge Q&A.

        Used when the user has a locked template and asks usage questions.

        Args:
            template_context: Full template metadata (params, concepts, etc.).

        Returns:
            System prompt for answer_question() with locked_template set.
        """
        return self._assemble(
            _TEMPLATE_QA_SYSTEM,
            _format_template_context(template_context),
        )

    # ── Scenario 3: GIS-expert Q&A ────────────────────────────────────────

    def build_gis_expert_prompt(self) -> str:
        """Build system prompt for GIS-expert Q&A.

        Used when the user asks a general GIS question with no template locked.

        Returns:
            System prompt for answer_question() with no template context.
        """
        return self._assemble(_GIS_EXPERT_SYSTEM)

    # ── Scenario 4: Parameter extraction ──────────────────────────────────

    def build_param_prompt(self, task_context: str) -> str:
        """Build system prompt for parameter extraction.

        Args:
            task_context: Template ID, current params, and param schema.

        Returns:
            System prompt for extract_params().
        """
        return self._assemble(
            _PARAM_SYSTEM,
            _format_task_context(task_context),
        )

    # ── Scenario 5: Error diagnosis ───────────────────────────────────────

    def build_diagnosis_prompt(self, task_context: str) -> str:
        """Build system prompt for execution error diagnosis.

        Args:
            task_context: Error diagnosis task description.

        Returns:
            System prompt for analyze_execution_error().
        """
        return self._assemble(
            _DIAGNOSIS_SYSTEM,
            _format_task_context(task_context),
        )
