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
from core.models import Session, SessionState
from core.workspace import WorkspaceNotFoundError
from llm.intent import classify_intent
from llm.models import Message, TemplateInfo
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

    # Extract script preview if in SCRIPT_PREVIEW state
    script_preview: Optional[str] = None
    if session.state == SessionState.SCRIPT_PREVIEW and template:
        try:
            engine = get_template_engine()
            rendered = engine.render(template, session.params)
            script_preview = rendered.content.strip()
        except Exception:
            script_preview = None

    # Get current workspace absolute path
    from api.dependencies import get_workspace

    workspace_path = str(get_workspace().root)

    return SessionResponse(
        session_id=session_id,
        state=session.state.name,
        task_context=task_context,
        script_preview=script_preview,
        error_context=None,
        history=history,
        workspace=workspace_path,
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
    - Q&A question → IDLE with text reply
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

    # --- Route 1: Q&A question → IDLE with text reply ---
    _EXPLORATORY_MARKERS = {
        "什么", "哪些", "怎么", "如何", "为什么", "能否", "可以",
        "支持", "介绍", "说明", "解释", "了解", "知道",
    }
    _QUESTION_PATTERNS = ("?", "？", "吗", "么", "呢", "吧")
    is_question = (
        user_input.endswith(_QUESTION_PATTERNS)
        or any(m in user_input_lower for m in _EXPLORATORY_MARKERS)
    )

    if is_question:
        context_templates = [t for t, s in scored if s > 0][:5]
        if not context_templates and all_templates:
            context_templates = all_templates[:3]

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
            )
        except Exception as exc:
            logger.warning("LLM Q&A failed: %s", exc)
            reply = (
                "抱歉，当前无法调用 LLM 回答你的问题。"
                "你可以从左栏浏览模板卡片，或直接描述具体数据处理需求。"
            )

        new_session = (
            session.with_state(SessionState.IDLE)
            .with_history(
                Message(role="user", content=request.input)
            )
            .with_history(
                Message(role="agent", content=reply)
            )
        )
        session_manager.update_session(session_id, new_session)
        return _build_session_response(session_id, new_session)

    # --- Route 2: Fast path — strong keyword match (score ≥ 8) ---
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

    # --- Route 3: Two-stage matching (coarse + LLM fine-rank) ---
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

    # 3a: Absolute advantage — LLM confidence ≥ 0.85 → auto-select
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

    # 3b: Strong match — LLM confidence ≥ 0.5 → show top-1 as primary
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

    # 3c: Weak/unknown match → show top-3 keyword candidates
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

    new_session = session.with_state(SessionState.PARAM_COLLECT).with_template(template)
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
        new_session = session.with_state(SessionState.PARAM_COLLECT)
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
    new_session = session.with_state(SessionState.SCRIPT_PREVIEW)
    for name, value in valid_params.items():
        new_session = new_session.with_param(name, value)
    session_manager.update_session(session_id, new_session)
    return _build_session_response(session_id, new_session)


@router.post("/{session_id}/execute", response_model=None)
async def execute_script(
    session_id: str,
    dry_run: bool = False,
    session_manager: SessionManager = Depends(get_session_manager),
) -> Union[DryRunResponse, JSONResponse]:
    """Trigger script execution.

    Actual execution is handled via WebSocket (T-UX-05).
    This endpoint only triggers or previews.

    Args:
        session_id: Session UUID.
        dry_run: If True, return preview without triggering execution.
        session_manager: SessionManager dependency.

    Returns:
        ExecutionTriggerResponse or DryRunResponse.
    """
    session = _get_session_or_404(session_id, session_manager)

    if dry_run:
        script_preview = None
        if session.template:
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


@router.post("/{session_id}/workspace", response_model=SessionResponse)
async def update_session_workspace(
    session_id: str,
    request: WorkspaceRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> SessionResponse:
    """Update workspace path, reset session, and recreate dependent components.

    Validates that the new path exists and is a directory before switching.
    Clears the session state as a side effect.

    Args:
        session_id: Session UUID.
        request: WorkspaceRequest with new path.
        session_manager: SessionManager dependency.

    Returns:
        Cleared SessionResponse with new workspace context.

    Raises:
        HTTPException: 400 if path invalid, 404 if session not found.
    """
    _get_session_or_404(session_id, session_manager)

    try:
        new_path = Path(request.path).resolve()
        update_workspace(new_path)
    except WorkspaceNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid workspace path: {exc}"
        ) from exc

    session_manager.clear_session(session_id)
    cleared = session_manager.get_session(session_id)
    assert cleared is not None
    return _build_session_response(session_id, cleared)
