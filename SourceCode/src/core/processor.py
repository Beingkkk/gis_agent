"""Session state machine processor for GIS Agent.

Orchestrates intent classification, parameter extraction, validation,
and script rendering across the conversation lifecycle.

Public API:
    SessionProcessor — processes user input and drives state transitions

Design: plan-core v1.0.0 (DC-0040, DC-0043, DC-0044)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional, Tuple

from core.models import ExecutionErrorContext, Session, SessionState
from core.registry import TemplateRegistry
from core.validator import ParamValidator
from llm.client import LLMClient
from llm.diagnosis import analyze_execution_error
from llm.intent import classify_intent
from llm.keywords import extract_keywords
from llm.models import ErrorDiagnosis, Message, TemplateInfo
from llm.params import extract_params
from llm.prompts import PromptBuilder
from llm.qa import answer_question
from rag.retriever import DocumentRetriever

if TYPE_CHECKING:
    from core.models import TemplateDef
    from templates.engine import TemplateEngine

logger = logging.getLogger(__name__)


class SessionProcessor:
    """会话状态处理器。

    封装状态机逻辑，将用户输入转化为状态转换和响应。

    Design:
        DC-0040, DC-0043, DC-0044
    """

    # Confidence threshold for intent classification (plan-core DC-0044)
    _CONFIDENCE_THRESHOLD = 0.7

    def __init__(
        self,
        registry: TemplateRegistry,
        validator: ParamValidator,
        template_engine: TemplateEngine,
        llm_client: LLMClient,
        prompt_builder: PromptBuilder,
        retriever: Optional[DocumentRetriever] = None,
    ) -> None:
        """注入依赖。

        Args:
            registry: 模板注册表，用于查询模板定义。
            validator: 参数校验器，用于校验用户提供的参数值。
            template_engine: 模板引擎，用于渲染 GDAL 脚本。
            llm_client: LLM 客户端，用于意图分类和参数抽取。
            prompt_builder: Prompt 构建器，用于组装 LLM 系统提示词。
            retriever: RAG 检索器，用于文档问答。为 None 时问答功能不可用。
        """
        self._registry = registry
        self._validator = validator
        self._template_engine = template_engine
        self._llm_client = llm_client
        self._prompt_builder = prompt_builder
        self._retriever = retriever

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_param_prompt(template: "TemplateDef") -> str:
        """Build a human-readable parameter list for a template.

        Called when entering PARAM_COLLECT so the user knows what
        to input next.
        """
        lines = [f"已识别任务：{template.name}。\n"]
        if template.params:
            lines.append("请输入以下参数：")
            for p in template.params:
                tag = "必填" if p.required else "可选"
                if p.default is not None:
                    tag += f"，默认 {p.default}"
                lines.append(f"  • {p.name}（{tag}）：{p.description}")
        else:
            lines.append("该任务无需额外参数。")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, session: Session, user_input: str) -> Tuple[Session, str]:
        """处理一轮用户输入，返回新状态和响应文本。

        Args:
            session: 当前会话状态。
            user_input: 用户输入文本（空字符串表示仅刷新状态）。

        Returns:
            (new_session, response_text)
            response_text 是展示给用户的自然语言响应。

        Raises:
            ValueError: session.state 为无效状态。
        """
        handlers = {
            SessionState.IDLE: self._handle_idle,
            SessionState.INTENT_CONFIRM: self._handle_intent_confirm,
            SessionState.PARAM_COLLECT: self._handle_param_collect,
            SessionState.SCRIPT_PREVIEW: self._handle_script_preview,
            SessionState.ERROR_RECOVERY: self._handle_error_recovery,
        }
        handler = handlers.get(session.state)
        if handler is None:
            raise ValueError(f"Invalid session state: {session.state}")
        return handler(session, user_input)

    # ------------------------------------------------------------------
    # State handlers
    # ------------------------------------------------------------------

    def _handle_idle(
        self,
        session: Session,
        user_input: str,
    ) -> Tuple[Session, str]:
        """空闲状态：进行意图分类。

        - 高置信度（>=0.7）→ PARAM_COLLECT，告知用户已识别的任务
        - 低置信度（<0.7）→ INTENT_CONFIRM，列出候选模板让用户选择
        - 无匹配 → 保持在 IDLE，提示无法识别
        """
        if not user_input.strip():
            return (session, "请输入您的需求，或输入 /help 查看可用命令。")

        available = self._registry.list_templates()
        template_infos = [
            TemplateInfo(id=t.id, name=t.name, description=t.description)
            for t in available
        ]
        # Add virtual QA template so LLM can route questions to RAG
        template_infos.insert(
            0,
            TemplateInfo(
                id="__qa__",
                name="文档问答",
                description="基于本地GDAL文档回答用户关于工具、格式、参数的使用问题",
            ),
        )

        result = classify_intent(
            user_input=user_input,
            available_templates=template_infos,
            history=session.history,
            client=self._llm_client,
            builder=self._prompt_builder,
        )

        if not result.template_id:
            # LLM returned empty template_id → show candidates for user to choose
            candidates = self._registry.list_templates()
            lines = [f"{i + 1}. {t.name}" for i, t in enumerate(candidates)]
            response = (
                f"您的需求「{user_input}」暂没有完全匹配的模板。\n"
                f"以下是目前可用的功能，请选择最接近的一项：\n"
                + "\n".join(lines)
                + "\n\n或请重新描述您的需求。"
            )
            new_session = (
                session.with_state(SessionState.INTENT_CONFIRM)
                .with_template(None)
                .with_candidates(candidates)
            )
            return (new_session, response)

        # QA route: user is asking a question about GDAL/tools/formats
        if result.template_id == "__qa__":
            # Require minimum confidence to avoid false-positive QA routing
            if result.confidence >= 0.3:
                if self._retriever is None:
                    return (session, "文档问答服务暂不可用，请稍后再试。")
                try:
                    # Keyword extraction → multi-query retrieval → synthesis
                    keywords = extract_keywords(
                        user_input=user_input,
                        history=session.history,
                        client=self._llm_client,
                        builder=self._prompt_builder,
                    )
                    docs = self._retriever.search_multi(keywords, top_k_per_query=2)
                    answer = answer_question(
                        user_input=user_input,
                        retrieved_docs=docs,
                        history=session.history,
                        client=self._llm_client,
                        builder=self._prompt_builder,
                    )
                    new_session = session.with_history(
                        Message(role="user", content=user_input)
                    )
                    new_session = new_session.with_history(
                        Message(role="assistant", content=answer)
                    )
                    return (new_session, answer)
                except Exception as exc:
                    logger.error("Q&A failed: %s", exc)
                    return (session, f"文档问答失败：{exc}")
            # confidence < 0.3 → fall through to low-confidence handling below

        if result.confidence < self._CONFIDENCE_THRESHOLD:
            # Low confidence → ask user to confirm from candidates
            candidates = self._registry.list_templates()
            lines = [f"{i + 1}. {t.name}" for i, t in enumerate(candidates)]
            response = (
                "暂时没有完全匹配的模板：\n"
                + "\n".join(lines)
                + "\n\n或请重新描述您的需求。"
            )
            new_session = (
                session.with_state(SessionState.INTENT_CONFIRM)
                .with_template(None)
                .with_candidates(candidates)
            )
            return (new_session, response)

        # High confidence → set template and move to param collection
        template = self._registry.get_template(result.template_id)
        if template is None:
            logger.warning("Classified template %s not in registry", result.template_id)
            return (session, "抱歉，识别的任务模板不可用，请重新描述。")

        new_session = (
            session.with_state(SessionState.PARAM_COLLECT)
            .with_template(template)
            .with_history(Message(role="user", content=user_input))
        )
        return (
            new_session,
            self._build_param_prompt(template),
        )

    # Keywords that indicate a user is asking a question, not selecting a task
    _QUESTION_KEYWORDS = (
        "如何", "怎么", "怎样", "什么", "为什么", "介绍", "说明", "解释",
        "哪些", "哪个", "谁", "什么时候", "哪里", "多少", "是否", "吗",
        "what", "how", "why", "explain", "describe", "which",
        "when", "where", "who", "介绍一下", "是什么", "什么意思", "怎么样",
    )

    # Keywords that indicate explicit denial
    _DENY_KEYWORDS = (
        "不", "否", "none", "no", "算了", "不要", "不用", "没", "没有",
        "都不是", "不对", "不对了", "不用了", "不要了",
    )

    def _handle_intent_confirm(
        self,
        session: Session,
        user_input: str,
    ) -> Tuple[Session, str]:
        """意图确认状态：用户从候选中选择或否认。

        - 用户选择模板（数字序号 / 名称 / ID）→ PARAM_COLLECT
        - 用户提问 → 回到 IDLE，将输入交给 Q&A 处理
        - 用户否认 → IDLE，提示重新描述需求
        """
        user_lower = user_input.strip().lower()
        candidates = session.candidates or self._registry.list_templates()

        # 1. Check if user selected a number
        if user_lower.isdigit():
            idx = int(user_lower) - 1
            if 0 <= idx < len(candidates):
                selected = candidates[idx]
                new_session = (
                    session.with_state(SessionState.PARAM_COLLECT)
                    .with_template(selected)
                    .with_candidates([])
                    .with_history(Message(role="user", content=user_input))
                )
                return (
                    new_session,
                    self._build_param_prompt(selected),
                )

        # 2. Check if user typed a template name or ID directly
        for candidate in candidates:
            if user_lower == candidate.id.lower() or user_lower == candidate.name.lower():
                new_session = (
                    session.with_state(SessionState.PARAM_COLLECT)
                    .with_template(candidate)
                    .with_candidates([])
                    .with_history(Message(role="user", content=user_input))
                )
                return (
                    new_session,
                    self._build_param_prompt(candidate),
                )

        # 3. Check if user is asking a question → route back to IDLE for re-classification
        if any(kw in user_lower for kw in self._QUESTION_KEYWORDS):
            return self._handle_idle(
                session.with_state(SessionState.IDLE)
                .with_template(None)
                .with_candidates([])
                .with_history(Message(role="user", content=user_input)),
                user_input,
            )

        # 4. Explicit denial → back to IDLE with hint
        if any(kw in user_lower for kw in self._DENY_KEYWORDS):
            return (
                session.with_state(SessionState.IDLE)
                .with_template(None)
                .with_candidates([])
                .with_history(Message(role="user", content=user_input)),
                "好的，请重新描述您的需求。",
            )

        # 5. Unknown input → treat as new intent, re-classify via _handle_idle
        return self._handle_idle(
            session.with_state(SessionState.IDLE)
            .with_template(None)
            .with_candidates([])
            .with_history(Message(role="user", content=user_input)),
            user_input,
        )

    def _handle_param_collect(
        self,
        session: Session,
        user_input: str,
    ) -> Tuple[Session, str]:
        """参数收集状态：抽取参数，检查完整性。

        - 参数完整且校验通过 → SCRIPT_PREVIEW，展示脚本
        - 有缺失参数 → 保持在 PARAM_COLLECT，追问缺失字段
        - 校验失败 → 保持在 PARAM_COLLECT，提示具体错误
        """
        template = session.template
        if template is None:
            logger.error("PARAM_COLLECT state with no template set")
            return (session.with_state(SessionState.IDLE), "会话状态异常，请重新开始。")

        # Build param schema for LLM
        param_schema = {
            p.name: {
                "type": p.type,
                "required": p.required,
                "description": p.description,
                "default": p.default,
            }
            for p in template.params
        }

        result = extract_params(
            user_input=user_input,
            template_id=template.id,
            param_schema=param_schema,
            current_params=session.params,
            history=session.history,
            client=self._llm_client,
            builder=self._prompt_builder,
        )

        # Validate extracted params
        merged_params = dict(session.params)
        merged_params.update(result.params)
        valid_params, errors = self._validator.validate_all(template, merged_params)

        if errors:
            # Validation failed → stay in PARAM_COLLECT with error messages
            error_text = "\n".join(errors)
            return (
                session.with_history(Message(role="user", content=user_input)),
                f"参数校验失败：\n{error_text}\n\n请修正后重试。",
            )

        if result.missing:
            # Still missing required params → stay in PARAM_COLLECT
            questions_text = (
                "\n".join(result.questions)
                if result.questions
                else (f"还缺少以下参数：{', '.join(result.missing)}")
            )
            new_session = session.with_history(Message(role="user", content=user_input))
            # Merge any newly extracted params
            for name, value in result.params.items():
                new_session = new_session.with_param(name, value)
            return (new_session, questions_text)

        # All params collected and valid → SCRIPT_PREVIEW
        try:
            rendered = self._template_engine.render(
                template, valid_params, platform=None
            )
        except Exception as exc:
            logger.error("Template rendering failed: %s", exc)
            return (
                session.with_history(Message(role="user", content=user_input)),
                f"脚本生成失败：{exc}\n\n请检查参数后重试。",
            )

        script_text = rendered.content.strip()
        response = (
            f"───────────────────────────────\n"
            f"脚本预览：\n"
            f"───────────────────────────────\n"
            f"{script_text}\n"
            f"───────────────────────────────"
        )

        new_session = session.with_state(SessionState.SCRIPT_PREVIEW).with_history(
            Message(role="user", content=user_input)
        )
        for name, value in valid_params.items():
            new_session = new_session.with_param(name, value)
        return (new_session, response)

    def _handle_script_preview(
        self,
        session: Session,
        user_input: str,
    ) -> Tuple[Session, str]:
        """脚本展示状态：生成脚本展示文本。

        本方法**不处理** Y/N 确认交互（由 CLI 层的 REPL 负责）。
        仅负责调用模板引擎渲染脚本，并返回展示文本。

        - 渲染成功 → 返回 (SCRIPT_PREVIEW, script_text)
        - 渲染失败 → 返回 (PARAM_COLLECT, 错误提示)
        """
        template = session.template
        if template is None:
            logger.error("SCRIPT_PREVIEW state with no template set")
            return (session.with_state(SessionState.IDLE), "会话状态异常，请重新开始。")

        try:
            rendered = self._template_engine.render(
                template, session.params, platform=None
            )
        except Exception as exc:
            logger.error("Template rendering failed: %s", exc)
            return (
                session.with_state(SessionState.PARAM_COLLECT),
                f"脚本生成失败：{exc}\n\n请检查参数后重试。",
            )

        script_text = rendered.content.strip()
        response = (
            f"───────────────────────────────\n"
            f"脚本预览：\n"
            f"───────────────────────────────\n"
            f"{script_text}\n"
            f"───────────────────────────────"
        )
        return (session, response)

    def _build_diagnosis_context(self, session: Session) -> str:
        """Build diagnosis context string for LLM error analysis.

        Includes template info, param definitions, current values,
        and rendered script content.

        Design:
            DC-0049
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
            rendered = self._template_engine.render(
                template, session.params, platform=None
            )
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

    def _build_recovery_response(
        self, diagnosis: ErrorDiagnosis, current_params: dict[str, str]
    ) -> str:
        """Build user-facing recovery response with diagnosis + options.

        Design:
            DC-0049
        """
        lines: list[str] = [
            "───────────────────────────────",
            "执行失败诊断",
            "",
            f"原因：{diagnosis.cause}",
            f"建议：{diagnosis.suggestion}",
            "",
        ]

        if diagnosis.fixed_params:
            lines.append("修正后参数预览：")
            # Show all params, with fixed ones highlighted
            for name, value in current_params.items():
                marker = " → " + diagnosis.fixed_params[name] if name in diagnosis.fixed_params else ""
                lines.append(f"  {name}: {value}{marker}")
            for name, value in diagnosis.fixed_params.items():
                if name not in current_params:
                    lines.append(f"  {name}: (新增) {value}")
            lines.append("")

        lines.append("请选择：")
        if diagnosis.can_auto_fix:
            lines.append("1. 确认修正（重新生成脚本预览）")
        lines.append("2. 手动修改参数")
        lines.append("3. 放弃任务")
        lines.append("───────────────────────────────")

        return "\n".join(lines)

    def _handle_error_recovery(
        self,
        session: Session,
        user_input: str,
    ) -> Tuple[Session, str]:
        """错误恢复状态：LLM 诊断 + 用户选择修复路径。

        首次进入（error_context.diagnosis is None）：
            - 调用 analyze_execution_error() 获取诊断
            - 显示诊断结果 + 选项菜单
            - 保持在 ERROR_RECOVERY

        用户已看到诊断，输入选择：
            - "1"/"Y"/"确认"/"是" + can_auto_fix=True → 应用 fixed_params → SCRIPT_PREVIEW
            - "2"/"手动"/"修改" → PARAM_COLLECT（保留现有参数，清除 error_context）
            - "3"/"放弃"/"N"/"否"/"算了" → IDLE（清除 template、params、error_context）
            - 其他输入 → 当作参数修改 → PARAM_COLLECT（清除 error_context）

        Design:
            DC-0048, DC-0049
        """
        error_ctx = session.error_context
        if error_ctx is None:
            logger.error("ERROR_RECOVERY state with no error_context set")
            return (
                session.with_state(SessionState.IDLE),
                "会话状态异常，请重新开始。",
            )

        # First entry: diagnosis not yet performed
        if error_ctx.diagnosis is None:
            diagnosis_context = self._build_diagnosis_context(session)
            try:
                diagnosis = analyze_execution_error(
                    returncode=error_ctx.returncode,
                    stdout=error_ctx.stdout,
                    stderr=error_ctx.stderr,
                    diagnosis_context=diagnosis_context,
                    history=session.history,
                    client=self._llm_client,
                    builder=self._prompt_builder,
                )
            except Exception as exc:
                logger.error("LLM diagnosis failed: %s", exc)
                diagnosis = ErrorDiagnosis(
                    cause="诊断失败，无法自动分析错误原因。",
                    suggestion="请检查上方错误输出，或尝试手动修改参数后重试。",
                    fixed_params={},
                    confidence=0.0,
                    can_auto_fix=False,
                )

            new_error_ctx = ExecutionErrorContext(
                returncode=error_ctx.returncode,
                stdout=error_ctx.stdout,
                stderr=error_ctx.stderr,
                duration_ms=error_ctx.duration_ms,
                diagnosis=diagnosis,
            )
            new_session = session.with_error(new_error_ctx)
            response = self._build_recovery_response(diagnosis, session.params)
            return (new_session, response)

        # User has seen diagnosis, parse their choice
        diagnosis = error_ctx.diagnosis
        user_lower = user_input.strip().lower()

        # Option 1: Confirm auto-fix
        if (
            user_lower in ("1", "y", "确认", "是", "yes")
            and diagnosis.can_auto_fix
        ):
            new_session = (
                session.clear_error()
                .with_state(SessionState.SCRIPT_PREVIEW)
                .with_history(Message(role="user", content=user_input))
            )
            for name, value in diagnosis.fixed_params.items():
                new_session = new_session.with_param(name, value)

            # Render script with fixed params
            template = new_session.template
            if template is None:
                logger.error("ERROR_RECOVERY auto-fix with no template")
                return (
                    new_session.with_state(SessionState.IDLE),
                    "会话状态异常，请重新开始。",
                )

            try:
                rendered = self._template_engine.render(
                    template, new_session.params, platform=None
                )
            except Exception as exc:
                logger.error("Template rendering failed after auto-fix: %s", exc)
                return (
                    new_session.with_state(SessionState.PARAM_COLLECT),
                    f"脚本生成失败：{exc}\n\n请检查参数后重试。",
                )

            script_text = rendered.content.strip()
            response = (
                f"───────────────────────────────\n"
                f"脚本预览（已自动修正参数）：\n"
                f"───────────────────────────────\n"
                f"{script_text}\n"
                f"───────────────────────────────"
            )
            return (new_session, response)

        # Option 2: Manual edit
        if user_lower in ("2", "手动", "修改"):
            return (
                session.clear_error()
                .with_state(SessionState.PARAM_COLLECT)
                .with_history(Message(role="user", content=user_input)),
                "请修改参数，或重新描述您的需求。",
            )

        # Option 3: Abandon
        if user_lower in ("3", "放弃", "n", "否", "算了", "no"):
            new_session = (
                Session(state=SessionState.IDLE, history=list(session.history))
                .with_history(Message(role="user", content=user_input))
            )
            return (new_session, "已放弃当前任务。请描述新的需求。")

        # Unknown input: treat as parameter modification
        return self._handle_param_collect(
            session.clear_error()
            .with_state(SessionState.PARAM_COLLECT)
            .with_history(Message(role="user", content=user_input)),
            user_input,
        )
