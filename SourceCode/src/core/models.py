"""Core data models for GIS Agent.

Provides TemplateDef, ParamDef, SessionState, and Session dataclasses
used by core/, templates/, and cli/ modules.

Public API:
    ParamDef — parameter definition
    TemplateDef — template definition
    SessionState — session state enum
    Session — immutable session context

Design: plan-core v1.0.0 (DC-0040, DC-0041, DC-0043)
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    # Forward reference for exec_env to avoid circular imports
    from core.exec_env import ExecEnvironment
    from llm.models import ErrorDiagnosis, Message


# ---------------------------------------------------------------------------
# Template / Parameter definitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParamDef:
    """Parameter definition (from template registry).

    Design:
        DC-0041, DC-0091
    """

    name: str
    type: str
    required: bool
    description: str
    default: Optional[str] = None
    must_exist: bool = False
    options: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class TemplateDef:
    """Template definition (from template registry).

    Design:
        DC-0041, DC-0055, DC-0090
    """

    id: str
    name: str
    description: str
    template_file: str
    params: List[ParamDef] = field(default_factory=list)
    # Knowledge metadata fields (ADR-0001 / DC-0055)
    concepts: List[tuple[str, str]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    seealso: List[str] = field(default_factory=list)
    common_errors: List[tuple[str, str]] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExecutionErrorContext:
    """执行错误的上下文信息，附加在 Session 上供 ERROR_RECOVERY 使用。

    Design:
        DC-0048
    """

    returncode: int
    stdout: str
    stderr: str
    duration_ms: int
    diagnosis: Optional["ErrorDiagnosis"] = None


# ---------------------------------------------------------------------------
# Session state machine
# ---------------------------------------------------------------------------


class SessionState(Enum):
    """会话状态。

    Design:
        DC-0040
    """

    IDLE = auto()
    INTENT_CONFIRM = auto()
    PARAM_COLLECT = auto()
    SCRIPT_PREVIEW = auto()
    EXECUTING = auto()
    ERROR_RECOVERY = auto()


@dataclass(frozen=True)
class Session:
    """会话上下文。

    不可变对象：每次状态转换生成新的 Session 实例。

    Design:
        DC-0043
    """

    state: SessionState = SessionState.IDLE
    history: List["Message"] = field(default_factory=list)  # Discovery/Exec
    qa_history: List["Message"] = field(default_factory=list)  # QATab (DC-0107)
    template: Optional[TemplateDef] = None
    params: Dict[str, str] = field(default_factory=dict)
    candidates: List[TemplateDef] = field(default_factory=list)
    error_context: Optional[ExecutionErrorContext] = None
    user_script: Optional[str] = None
    exec_env: Optional["ExecEnvironment"] = None  # DC-0104

    def with_state(self, state: SessionState) -> "Session":
        """返回状态变更后的新 Session。"""
        return Session(
            state=state,
            history=self.history,
            qa_history=self.qa_history,
            template=self.template,
            params=self.params,
            candidates=self.candidates,
            error_context=self.error_context,
            user_script=self.user_script,
            exec_env=self.exec_env,
        )

    def with_template(self, template: Optional[TemplateDef]) -> "Session":
        """返回选定模板后的新 Session。"""
        return Session(
            state=self.state,
            history=self.history,
            qa_history=self.qa_history,
            template=template,
            params=self.params,
            candidates=self.candidates,
            error_context=self.error_context,
            user_script=self.user_script,
            exec_env=self.exec_env,
        )

    def with_param(self, name: str, value: str) -> "Session":
        """返回添加参数后的新 Session。"""
        new_params = dict(self.params)
        new_params[name] = value
        return Session(
            state=self.state,
            history=self.history,
            qa_history=self.qa_history,
            template=self.template,
            params=new_params,
            candidates=self.candidates,
            error_context=self.error_context,
            user_script=self.user_script,
            exec_env=self.exec_env,
        )

    def with_history(self, message: "Message") -> "Session":
        """返回追加消息后的新 Session（Discovery/Exec 流程）。"""
        new_history = list(self.history)
        new_history.append(message)
        return Session(
            state=self.state,
            history=new_history,
            qa_history=self.qa_history,
            template=self.template,
            params=self.params,
            candidates=self.candidates,
            error_context=self.error_context,
            user_script=self.user_script,
            exec_env=self.exec_env,
        )

    def with_qa_history(self, message: "Message") -> "Session":
        """返回追加 QA 消息后的新 Session（QATab 专属，DC-0107）。"""
        new_qa = list(self.qa_history)
        new_qa.append(message)
        return Session(
            state=self.state,
            history=self.history,
            qa_history=new_qa,
            template=self.template,
            params=self.params,
            candidates=self.candidates,
            error_context=self.error_context,
            user_script=self.user_script,
            exec_env=self.exec_env,
        )

    def with_candidates(self, candidates: List[TemplateDef]) -> "Session":
        """返回更新候选项后的新 Session。"""
        return Session(
            state=self.state,
            history=self.history,
            qa_history=self.qa_history,
            template=self.template,
            params=self.params,
            candidates=list(candidates),
            error_context=self.error_context,
            user_script=self.user_script,
            exec_env=self.exec_env,
        )

    def with_error(self, error_context: Optional[ExecutionErrorContext]) -> "Session":
        """附加/更新错误上下文。

        Design:
            DC-0048
        """
        return Session(
            state=self.state,
            history=self.history,
            qa_history=self.qa_history,
            template=self.template,
            params=self.params,
            candidates=self.candidates,
            error_context=error_context,
            user_script=self.user_script,
            exec_env=self.exec_env,
        )

    def with_user_script(self, user_script: Optional[str]) -> "Session":
        """设置用户编辑后的脚本（覆盖模板渲染结果）。

        Design:
            DC-UX-11 (命令编辑)
        """
        return Session(
            state=self.state,
            history=self.history,
            qa_history=self.qa_history,
            template=self.template,
            params=self.params,
            candidates=self.candidates,
            error_context=self.error_context,
            user_script=user_script,
            exec_env=self.exec_env,
        )

    def with_exec_env(self, exec_env: Optional["ExecEnvironment"]) -> "Session":
        """设置执行环境。

        Design:
            DC-0104
        """
        return Session(
            state=self.state,
            history=self.history,
            qa_history=self.qa_history,
            template=self.template,
            params=self.params,
            candidates=self.candidates,
            error_context=self.error_context,
            user_script=self.user_script,
            exec_env=exec_env,
        )

    def clear_error(self) -> "Session":
        """清除错误上下文（恢复成功或放弃任务时）。

        Design:
            DC-0048
        """
        return Session(
            state=self.state,
            history=self.history,
            qa_history=self.qa_history,
            template=self.template,
            params=self.params,
            candidates=self.candidates,
            error_context=None,
            user_script=self.user_script,
            exec_env=self.exec_env,
        )

    def clear_history(self) -> "Session":
        """清空对话历史（执行断点后重置上下文）。

        Design:
            DC-0067
        """
        return Session(
            state=self.state,
            history=[],
            qa_history=self.qa_history,
            template=self.template,
            params=self.params,
            candidates=self.candidates,
            error_context=self.error_context,
            user_script=self.user_script,
            exec_env=self.exec_env,
        )

    def clear_qa_history(self) -> "Session":
        """清空 QA 对话历史（QATab 一键清空，DC-0107）。"""
        return Session(
            state=self.state,
            history=self.history,
            qa_history=[],
            template=self.template,
            params=self.params,
            candidates=self.candidates,
            error_context=self.error_context,
            user_script=self.user_script,
            exec_env=self.exec_env,
        )

    def clear_user_script(self) -> "Session":
        """清除用户编辑的脚本（如返回修改参数时）。

        Design:
            DC-UX-11
        """
        return Session(
            state=self.state,
            history=self.history,
            qa_history=self.qa_history,
            template=self.template,
            params=self.params,
            candidates=self.candidates,
            error_context=self.error_context,
            user_script=None,
            exec_env=self.exec_env,
        )
