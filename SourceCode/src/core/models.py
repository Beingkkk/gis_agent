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
    from llm.models import ErrorDiagnosis, Message


# ---------------------------------------------------------------------------
# Template / Parameter definitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParamDef:
    """Parameter definition (from template registry).

    Design:
        DC-0041
    """

    name: str
    type: str
    required: bool
    description: str
    default: Optional[str] = None
    must_exist: bool = False


@dataclass(frozen=True)
class TemplateDef:
    """Template definition (from template registry).

    Design:
        DC-0041
    """

    id: str
    name: str
    description: str
    template_file: str
    params: List[ParamDef] = field(default_factory=list)


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
    history: List["Message"] = field(default_factory=list)
    template: Optional[TemplateDef] = None
    params: Dict[str, str] = field(default_factory=dict)
    candidates: List[TemplateDef] = field(default_factory=list)
    error_context: Optional[ExecutionErrorContext] = None

    def with_state(self, state: SessionState) -> "Session":
        """返回状态变更后的新 Session。"""
        return Session(
            state=state,
            history=self.history,
            template=self.template,
            params=self.params,
            candidates=self.candidates,
            error_context=self.error_context,
        )

    def with_template(self, template: Optional[TemplateDef]) -> "Session":
        """返回选定模板后的新 Session。"""
        return Session(
            state=self.state,
            history=self.history,
            template=template,
            params=self.params,
            candidates=self.candidates,
            error_context=self.error_context,
        )

    def with_param(self, name: str, value: str) -> "Session":
        """返回添加参数后的新 Session。"""
        new_params = dict(self.params)
        new_params[name] = value
        return Session(
            state=self.state,
            history=self.history,
            template=self.template,
            params=new_params,
            candidates=self.candidates,
            error_context=self.error_context,
        )

    def with_history(self, message: "Message") -> "Session":
        """返回追加消息后的新 Session。"""
        new_history = list(self.history)
        new_history.append(message)
        return Session(
            state=self.state,
            history=new_history,
            template=self.template,
            params=self.params,
            candidates=self.candidates,
            error_context=self.error_context,
        )

    def with_candidates(self, candidates: List[TemplateDef]) -> "Session":
        """返回更新候选项后的新 Session。"""
        return Session(
            state=self.state,
            history=self.history,
            template=self.template,
            params=self.params,
            candidates=list(candidates),
            error_context=self.error_context,
        )

    def with_error(
        self, error_context: Optional[ExecutionErrorContext]
    ) -> "Session":
        """附加/更新错误上下文。

        Design:
            DC-0048
        """
        return Session(
            state=self.state,
            history=self.history,
            template=self.template,
            params=self.params,
            candidates=self.candidates,
            error_context=error_context,
        )

    def clear_error(self) -> "Session":
        """清除错误上下文（恢复成功或放弃任务时）。

        Design:
            DC-0048
        """
        return Session(
            state=self.state,
            history=self.history,
            template=self.template,
            params=self.params,
            candidates=self.candidates,
            error_context=None,
        )
