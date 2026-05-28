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

from core.models import Session, SessionState
from core.registry import TemplateRegistry
from core.validator import ParamValidator
from llm.client import LLMClient
from llm.intent import classify_intent
from llm.keywords import extract_keywords
from llm.models import Message, TemplateInfo
from llm.params import extract_params
from llm.prompts import PromptBuilder
from llm.qa import answer_question
from rag.retriever import DocumentRetriever

if TYPE_CHECKING:
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

    def _handle_intent_confirm(
        self,
        session: Session,
        user_input: str,
    ) -> Tuple[Session, str]:
        """意图确认状态：用户从候选中选择或否认。

        - 用户选择模板 → PARAM_COLLECT
        - 用户否认 → IDLE，提示重新描述需求
        """
        user_lower = user_input.strip().lower()

        # Check if user selected a number
        if user_lower.isdigit():
            idx = int(user_lower) - 1
            candidates = session.candidates or self._registry.list_templates()
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

        # User denied or invalid selection → back to IDLE
        return (
            session.with_state(SessionState.IDLE)
            .with_template(None)
            .with_candidates([])
            .with_history(Message(role="user", content=user_input)),
            "好的，请重新描述您的需求。",
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
            f"───────────────────────────────\n"
            f"\n确认执行？(Y/N)："
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
            f"───────────────────────────────\n"
            f"\n确认执行？(Y/N)："
        )
        return (session, response)
