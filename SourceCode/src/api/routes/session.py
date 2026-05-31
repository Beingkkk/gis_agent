"""Session REST API routes.

Provides endpoints for session lifecycle management:
create, intent processing, template locking, parameter submission,
execution triggering, and session clearing.

Design:
    T-UX-02 (DC-UX-02, DC-UX-03)
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Optional, Union

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.dependencies import (
    SessionManager,
    get_llm_client,
    get_prompt_builder,
    get_registry,
    get_session_manager,
    get_template_engine,
    get_validator,
    update_workspace,
)
from core.matching import score_template_match
from core.models import ExecutionErrorContext, Session, SessionState
from core.workspace import WorkspaceNotFoundError
from llm.diagnosis import analyze_execution_error
from llm.intent import classify_intent
from llm.models import ErrorDiagnosis, Message, TemplateInfo
from llm.qa import answer_question

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/session", tags=["session"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class SessionResponse(BaseModel):
    """Session snapshot returned to the frontend."""

    session_id: str
    state: str
    task_context: dict[str, Any]
    script_preview: Optional[str]
    error_context: Optional[dict[str, Any]]
    history: list[dict[str, str]]
    workspace: str
    user_script: Optional[str] = None


class IntentRequest(BaseModel):
    """User natural language input for intent classification."""

    input: str


class LockRequest(BaseModel):
    """Template selection confirmation."""

    template_id: str


class ParamsRequest(BaseModel):
    """Parameter submission."""

    params: dict[str, str]


class WorkspaceRequest(BaseModel):
    """Workspace path update."""

    path: str


class ExecutionTriggerResponse(BaseModel):
    """Execution trigger response."""

    execution_id: str
    message: str


class DryRunResponse(BaseModel):
    """Dry-run preview response."""

    dry_run: bool
    script_preview: Optional[str]
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_session_response(session_id: str, session: Session) -> SessionResponse:
    """Build SessionResponse from Session and session_id.

    Args:
        session_id: UUID string.
        session: Core Session instance.

    Returns:
        SessionResponse for JSON serialization.
    """
    template = session.template
    task_context: dict[str, Any] = {
        "template_id": template.id if template else None,
        "template_name": template.name if template else None,
        "params": dict(session.params),
        "missing_params": [],
    }

    # Calculate missing params if template is set
    if template and session.state in (SessionState.PARAM_COLLECT,):
        provided = set(session.params.keys())
        required = {p.name for p in template.params if p.required}
        task_context["missing_params"] = sorted(required - provided)

    # Always include candidates (empty list unless in INTENT_CONFIRM)
    task_context["candidates"] = [
        {
            "id": t.id,
            "name": t.name,
            "description": t.description,
        }
        for t in (
            session.candidates if session.state == SessionState.INTENT_CONFIRM else []
        )
    ]

    history = [{"role": msg.role, "content": msg.content} for msg in session.history]

    # Extract script preview: prioritize user-edited script (DC-UX-11)
    script_preview: Optional[str] = None
    if session.user_script:
        script_preview = session.user_script
    elif session.state == SessionState.SCRIPT_PREVIEW and template:
        try:
            engine = get_template_engine()
            rendered = engine.render(template, session.params)
            script_preview = rendered.content.strip()
        except Exception:
            script_preview = None

    # Get current workspace absolute path
    from api.dependencies import get_workspace

    workspace_path = str(get_workspace().root)

    # Build error_context if in ERROR_RECOVERY state
    error_context: Optional[dict[str, Any]] = None
    if session.error_context is not None:
        error_context = {
            "returncode": session.error_context.returncode,
            "stdout": session.error_context.stdout,
            "stderr": session.error_context.stderr,
            "duration_ms": session.error_context.duration_ms,
        }
        if session.error_context.diagnosis is not None:
            error_context["diagnosis"] = {
                "cause": session.error_context.diagnosis.cause,
                "suggestion": session.error_context.diagnosis.suggestion,
                "fixed_params": dict(session.error_context.diagnosis.fixed_params),
                "confidence": session.error_context.diagnosis.confidence,
                "can_auto_fix": session.error_context.diagnosis.can_auto_fix,
            }

    return SessionResponse(
        session_id=session_id,
        state=session.state.name,
        task_context=task_context,
        script_preview=script_preview,
        error_context=error_context,
        history=history,
        workspace=workspace_path,
        user_script=session.user_script,
    )


def _get_session_or_404(
    session_id: str,
    session_manager: SessionManager,
) -> Session:
    """Retrieve session or raise HTTP 404."""
    session = session_manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=SessionResponse)
async def create_session(
    workspace: Optional[str] = None,
    session_manager: SessionManager = Depends(get_session_manager),
) -> SessionResponse:
    """Create a new session.

    Args:
        workspace: Optional workspace path (accepted but not yet applied).
        session_manager: SessionManager dependency.

    Returns:
        SessionResponse with session_id and initial IDLE state.
    """
    session_id, session = session_manager.create_session()
    return _build_session_response(session_id, session)


# Thresholds for two-stage matching
_KEYWORD_HIGH_THRESHOLD = 8  # ~2-3 keyword hits → strong enough to skip LLM
_AUTO_SELECT_CONFIDENCE = 0.85  # LLM says clear winner → auto-select
_STRONG_MATCH_CONFIDENCE = 0.5  # LLM says likely match → show 1 candidate
_CANDIDATE_POOL_SIZE = 10  # Number of templates fed to LLM


@router.post("/{session_id}/intent", response_model=SessionResponse)
async def process_intent(
    session_id: str,
    request: IntentRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> SessionResponse:
    """Process user intent from natural language input.

    Two-stage matching:
    1. Coarse filter: score_template_match on ALL templates (fast, code-level)
    2. Fine ranking: classify_intent on top-N candidates (LLM semantic match)

    Routes:
    - Strong keyword match (score ≥ 8) → PARAM_COLLECT (fast path)
    - LLM confidence ≥ 0.85 → PARAM_COLLECT (auto-select, no user pick)
    - LLM confidence ≥ 0.5  → INTENT_CONFIRM with top-1 candidate
    - Otherwise              → INTENT_CONFIRM with top-3 candidates

    Args:
        session_id: Session UUID.
        request: IntentRequest with user input.
        session_manager: SessionManager dependency.

    Returns:
        Updated SessionResponse.
    """
    session = _get_session_or_404(session_id, session_manager)
    registry = get_registry()

    user_input = request.input.strip()
    user_input_lower = user_input.lower()
    if not user_input_lower:
        return _build_session_response(session_id, session)

    # --- Phase 0: Score ALL templates once (shared for all routes) ---
    all_templates = registry.list_templates()
    scored = [
        (t, score_template_match(t, user_input)) for t in all_templates
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    best_score = scored[0][1] if scored else 0

    # --- Route 1: Fast path — strong keyword match (score ≥ 8) ---
    # ~2-3 keyword hits → confident enough to skip LLM
    if best_score >= _KEYWORD_HIGH_THRESHOLD:
        best_template = scored[0][0]
        new_session = (
            session.with_state(SessionState.PARAM_COLLECT)
            .with_template(best_template)
            .with_history(
                Message(role="user", content=request.input)
            )
        )
        session_manager.update_session(session_id, new_session)
        return _build_session_response(session_id, new_session)

    # --- Route 2: Two-stage matching (coarse + LLM fine-rank) ---
    # Build candidate pool from top keyword-scored templates
    candidate_pool = [t for t, s in scored if s > 0][:_CANDIDATE_POOL_SIZE]
    if not candidate_pool:
        candidate_pool = all_templates[:_CANDIDATE_POOL_SIZE]

    # Prepare TemplateInfo for LLM intent classification
    template_infos = [
        TemplateInfo(
            id=t.id,
            name=t.name,
            description=t.description,
            keywords=list(t.keywords),
        )
        for t in candidate_pool
    ]

    # LLM fine-grained ranking within candidate pool
    llm_result = None
    try:
        llm_client = get_llm_client()
        prompt_builder = get_prompt_builder()
        llm_result = await asyncio.to_thread(
            classify_intent,
            user_input=user_input,
            available_templates=template_infos,
            history=list(session.history),
            client=llm_client,
            builder=prompt_builder,
        )
    except Exception as exc:
        logger.warning("LLM intent classification failed: %s", exc)

    # --- Decision: auto-select vs. recommend vs. show candidates ---

    # 2a: Absolute advantage — LLM confidence ≥ 0.85 → auto-select
    if llm_result and llm_result.confidence >= _AUTO_SELECT_CONFIDENCE:
        selected = registry.get_template(llm_result.template_id)
        if selected:
            logger.info(
                "Auto-selected template '%s' (confidence=%.2f) for: %s",
                selected.id,
                llm_result.confidence,
                user_input,
            )
            new_session = (
                session.with_state(SessionState.PARAM_COLLECT)
                .with_template(selected)
                .with_history(
                    Message(role="user", content=request.input)
                )
            )
            session_manager.update_session(session_id, new_session)
            return _build_session_response(session_id, new_session)

    # 2b: Strong match — LLM confidence ≥ 0.5 → show top-1 as primary
    if llm_result and llm_result.confidence >= _STRONG_MATCH_CONFIDENCE:
        selected = registry.get_template(llm_result.template_id)
        if selected:
            # Include selected as first, plus next best keyword candidates
            top_candidates = [selected]
            for t, s in scored:
                if t.id != selected.id and len(top_candidates) < 3:
                    top_candidates.append(t)
            new_session = (
                session.with_state(SessionState.INTENT_CONFIRM)
                .with_candidates(top_candidates)
                .with_history(
                    Message(role="user", content=request.input)
                )
            )
            session_manager.update_session(session_id, new_session)
            return _build_session_response(session_id, new_session)

    # 2c: Weak/unknown match → show top-3 keyword candidates
    top_candidates = [t for t, s in scored if s > 0][:3]
    if not top_candidates:
        top_candidates = all_templates[:3]

    new_session = (
        session.with_state(SessionState.INTENT_CONFIRM)
        .with_candidates(top_candidates)
        .with_history(
            Message(role="user", content=request.input)
        )
    )
    session_manager.update_session(session_id, new_session)
    return _build_session_response(session_id, new_session)


@router.post("/{session_id}/chat", response_model=SessionResponse)
async def chat_question(
    session_id: str,
    request: IntentRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> SessionResponse:
    """Handle Q&A from the QATab.

    Always treats input as a question — no intent matching or template
    search. If a template is locked, answers with full template context;
    otherwise answers as a GIS expert with no template context.

    Design: DC-UX-10 (GIS Q&A Tab)
    """
    session = _get_session_or_404(session_id, session_manager)
    registry = get_registry()
    user_input = request.input.strip()

    # Code-level branch: template-knowledge Q&A vs GIS-expert Q&A
    if session.template is not None:
        # Score remaining templates for supplementary context
        all_templates = registry.list_templates()
        scored = [
            (t, score_template_match(t, user_input))
            for t in all_templates
            if t.id != session.template.id
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        context_templates = [t for t, s in scored if s > 0][:3]
    else:
        context_templates = []

    try:
        llm_client = get_llm_client()
        prompt_builder = get_prompt_builder()
        reply = await asyncio.to_thread(
            answer_question,
            user_input=request.input,
            templates=context_templates,
            history=list(session.history),
            client=llm_client,
            builder=prompt_builder,
            locked_template=session.template,
            current_params=dict(session.params) if session.params else None,
        )
    except Exception as exc:
        logger.warning("LLM Q&A failed: %s", exc)
        reply = (
            "抱歉，当前无法调用 LLM 回答你的问题。"
            "请稍后重试。"
        )

    new_session = (
        session
        .with_history(
            Message(role="user", content=request.input)
        )
        .with_history(
            Message(role="assistant", content=reply)
        )
    )
    session_manager.update_session(session_id, new_session)
    return _build_session_response(session_id, new_session)


@router.post("/{session_id}/lock", response_model=SessionResponse)
async def lock_template(
    session_id: str,
    request: LockRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> SessionResponse:
    """Lock a template for the session.

    Args:
        session_id: Session UUID.
        request: LockRequest with template_id.
        session_manager: SessionManager dependency.

    Returns:
        Updated SessionResponse in PARAM_COLLECT state.

    Raises:
        HTTPException: 404 if session not found, 400 if template invalid.
    """
    session = _get_session_or_404(session_id, session_manager)
    registry = get_registry()

    template = registry.get_template(request.template_id)
    if template is None:
        raise HTTPException(
            status_code=400, detail=f"Template not found: {request.template_id}"
        )

    new_session = (
        session.with_state(SessionState.PARAM_COLLECT)
        .with_template(template)
        .clear_user_script()
    )
    session_manager.update_session(session_id, new_session)
    return _build_session_response(session_id, new_session)


@router.post("/{session_id}/params", response_model=SessionResponse)
async def submit_params(
    session_id: str,
    request: ParamsRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> SessionResponse:
    """Submit parameters for the current template.

    Validates parameters and either:
    - Returns SCRIPT_PREVIEW if all required params are valid
    - Returns PARAM_COLLECT with missing params listed

    Args:
        session_id: Session UUID.
        request: ParamsRequest with parameter key-value pairs.
        session_manager: SessionManager dependency.

    Returns:
        Updated SessionResponse.

    Raises:
        HTTPException: 400 if parameter validation fails.
    """
    session = _get_session_or_404(session_id, session_manager)
    template = session.template
    if template is None:
        raise HTTPException(status_code=400, detail="No template selected")

    # Merge existing params with newly submitted params
    merged_params = dict(session.params)
    merged_params.update(request.params)

    # Check for missing required params first (normal flow, not an error)
    provided = set(merged_params.keys())
    required = {p.name for p in template.params if p.required}
    missing = sorted(required - provided)

    if missing:
        new_session = (
            session.with_state(SessionState.PARAM_COLLECT)
            .clear_user_script()
        )
        for name, value in merged_params.items():
            new_session = new_session.with_param(name, value)
        session_manager.update_session(session_id, new_session)
        return _build_session_response(session_id, new_session)

    # All required params present → validate format
    validator = get_validator()
    valid_params, errors = validator.validate_all(template, merged_params)

    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    # All valid → SCRIPT_PREVIEW
    new_session = session.with_state(SessionState.SCRIPT_PREVIEW).clear_user_script()
    for name, value in valid_params.items():
        new_session = new_session.with_param(name, value)
    session_manager.update_session(session_id, new_session)
    return _build_session_response(session_id, new_session)


@router.post("/{session_id}/execute", response_model=None)
async def execute_script(
    session_id: str,
    dry_run: bool = False,
    script: Optional[str] = None,
    session_manager: SessionManager = Depends(get_session_manager),
) -> Union[DryRunResponse, JSONResponse]:
    """Trigger script execution.

    Actual execution is handled via WebSocket (T-UX-05).
    This endpoint only triggers or previews.

    Args:
        session_id: Session UUID.
        dry_run: If True, return preview without triggering execution.
        script: Optional user-edited script (overrides template rendering).
        session_manager: SessionManager dependency.

    Returns:
        ExecutionTriggerResponse or DryRunResponse.
    """
    session = _get_session_or_404(session_id, session_manager)

    # Store user-edited script if provided (DC-UX-11: 命令编辑)
    if script is not None:
        new_session = session.with_user_script(script.strip() or None)
        session_manager.update_session(session_id, new_session)
        session = new_session

    if dry_run:
        script_preview = None
        if session.user_script:
            script_preview = session.user_script
        elif session.template:
            try:
                engine = get_template_engine()
                rendered = engine.render(session.template, session.params)
                script_preview = rendered.content.strip()
            except Exception:
                script_preview = None
        return DryRunResponse(
            dry_run=True,
            script_preview=script_preview,
            message="Dry-run mode: script preview only",
        )

    import uuid as uuid_mod

    # Return with 202 Accepted status
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=202,
        content={
            "execution_id": str(uuid_mod.uuid4()),
            "message": "Execution triggered. Connect to WebSocket for live output.",
        },
    )


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    session_manager: SessionManager = Depends(get_session_manager),
) -> SessionResponse:
    """Get current session snapshot.

    Used by the frontend to refresh state after async operations
    such as WebSocket script execution.

    Args:
        session_id: Session UUID.
        session_manager: SessionManager dependency.

    Returns:
        Current SessionResponse snapshot.

    Raises:
        HTTPException: 404 if session not found.
    """
    session = _get_session_or_404(session_id, session_manager)
    return _build_session_response(session_id, session)


@router.post("/{session_id}/clear", response_model=SessionResponse)
async def clear_session(
    session_id: str,
    session_manager: SessionManager = Depends(get_session_manager),
) -> SessionResponse:
    """Clear session, resetting to IDLE.

    Args:
        session_id: Session UUID.
        session_manager: SessionManager dependency.

    Returns:
        SessionResponse in IDLE state.
    """
    _get_session_or_404(session_id, session_manager)
    session_manager.clear_session(session_id)
    cleared = session_manager.get_session(session_id)
    assert cleared is not None
    return _build_session_response(session_id, cleared)


def _build_diagnosis_context(session: Session) -> str:
    """Build diagnosis context string for LLM error analysis.

    Mirrors processor.py::_build_diagnosis_context (DC-0049).

    Args:
        session: Current Session with template and params.

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
        engine = get_template_engine()
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


@router.post("/{session_id}/diagnose", response_model=SessionResponse)
async def diagnose_execution(
    session_id: str,
    session_manager: SessionManager = Depends(get_session_manager),
) -> SessionResponse:
    """Trigger LLM diagnosis for the current execution error.

    Called by the frontend when session enters ERROR_RECOVERY with
    error_context.diagnosis = None. Performs LLM-driven analysis of
    the execution failure and stores the result back into the session.

    Args:
        session_id: Session UUID.
        session_manager: SessionManager dependency.

    Returns:
        Updated SessionResponse with diagnosis in error_context.

    Raises:
        HTTPException: 404 if session not found, 400 if not in
            ERROR_RECOVERY or diagnosis already exists.

    Design:
        plan-core DC-0049, plan-ux §4.1
    """
    session = _get_session_or_404(session_id, session_manager)

    if session.state != SessionState.ERROR_RECOVERY:
        raise HTTPException(
            status_code=400,
            detail=f"Session not in ERROR_RECOVERY state: {session.state.name}",
        )

    error_ctx = session.error_context
    if error_ctx is None:
        raise HTTPException(
            status_code=400, detail="No error context in session"
        )

    if error_ctx.diagnosis is not None:
        # Diagnosis already performed — return cached result
        return _build_session_response(session_id, session)

    # First-time diagnosis: build context and call LLM
    diagnosis_context = _build_diagnosis_context(session)
    try:
        diagnosis = await asyncio.to_thread(
            analyze_execution_error,
            returncode=error_ctx.returncode,
            stdout=error_ctx.stdout,
            stderr=error_ctx.stderr,
            diagnosis_context=diagnosis_context,
            history=list(session.history),
            client=get_llm_client(),
            builder=get_prompt_builder(),
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

    # Update session with diagnosis result
    new_error_ctx = ExecutionErrorContext(
        returncode=error_ctx.returncode,
        stdout=error_ctx.stdout,
        stderr=error_ctx.stderr,
        duration_ms=error_ctx.duration_ms,
        diagnosis=diagnosis,
    )
    new_session = session.with_error(new_error_ctx)
    session_manager.update_session(session_id, new_session)
    logger.info(
        "Execution diagnosis completed (session=%s, can_auto_fix=%s)",
        session_id,
        diagnosis.can_auto_fix,
    )

    return _build_session_response(session_id, new_session)


@router.post("/{session_id}/workspace", response_model=SessionResponse)
async def update_session_workspace(
    session_id: str,
    request: WorkspaceRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> SessionResponse:
    """Update workspace path and recreate dependent components.

    Validates that the new path exists and is a directory before switching.
    Preserves the current session state (template, params, history, etc.).

    Args:
        session_id: Session UUID.
        request: WorkspaceRequest with new path.
        session_manager: SessionManager dependency.

    Returns:
        SessionResponse with new workspace context, session state unchanged.

    Raises:
        HTTPException: 400 if path invalid, 404 if session not found.
    """
    session = _get_session_or_404(session_id, session_manager)

    try:
        new_path = Path(request.path).resolve()
        update_workspace(new_path)
    except WorkspaceNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid workspace path: {exc}"
        ) from exc

    return _build_session_response(session_id, session)
