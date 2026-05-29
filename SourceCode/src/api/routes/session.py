"""Session REST API routes.

Provides endpoints for session lifecycle management:
create, intent processing, template locking, parameter submission,
execution triggering, and session clearing.

Design:
    T-UX-02 (DC-UX-02, DC-UX-03)
"""

from typing import Any, Optional, Union

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.dependencies import (
    SessionManager,
    get_registry,
    get_session_manager,
    get_template_engine,
    get_validator,
)
from core.models import Session, SessionState

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


class IntentRequest(BaseModel):
    """User natural language input for intent classification."""

    input: str


class LockRequest(BaseModel):
    """Template selection confirmation."""

    template_id: str


class ParamsRequest(BaseModel):
    """Parameter submission."""

    params: dict[str, str]


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

    return SessionResponse(
        session_id=session_id,
        state=session.state.name,
        task_context=task_context,
        script_preview=script_preview,
        error_context=None,
        history=history,
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


@router.post("/{session_id}/intent", response_model=SessionResponse)
async def process_intent(
    session_id: str,
    request: IntentRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> SessionResponse:
    """Process user intent from natural language input.

    Simplified implementation: keyword-matches template name/id
    against available templates. Falls back to INTENT_CONFIRM
    with all templates as candidates.

    Args:
        session_id: Session UUID.
        request: IntentRequest with user input.
        session_manager: SessionManager dependency.

    Returns:
        Updated SessionResponse.
    """
    session = _get_session_or_404(session_id, session_manager)
    registry = get_registry()

    user_input = request.input.strip().lower()
    if not user_input:
        return _build_session_response(session_id, session)

    # Try keyword match against template names and ids
    for template in registry.list_templates():
        if template.id.lower() in user_input or template.name.lower() in user_input:
            new_session = (
                session.with_state(SessionState.PARAM_COLLECT)
                .with_template(template)
                .with_history(
                    __import__("llm.models", fromlist=["Message"]).Message(
                        role="user", content=request.input
                    )
                )
            )
            session_manager.update_session(session_id, new_session)
            return _build_session_response(session_id, new_session)

    # No match → INTENT_CONFIRM with all candidates
    candidates = registry.list_templates()
    new_session = (
        session.with_state(SessionState.INTENT_CONFIRM)
        .with_candidates(candidates)
        .with_history(
            __import__("llm.models", fromlist=["Message"]).Message(
                role="user", content=request.input
            )
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
