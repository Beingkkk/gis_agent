"""Pipeline REST API routes.

Provides endpoints for previewing and triggering multi-step
pipeline script execution.

Design:
    T-UX-06 (DC-UX-06)
"""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.dependencies import get_registry, get_template_engine

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class PipelineStepRequest(BaseModel):
    """A single step in a pipeline."""

    order: int
    template_id: str
    params: dict[str, str]


class DataLinkRequest(BaseModel):
    """Auto-link rule between pipeline steps."""

    fromStep: int
    fromParam: str
    toStep: int
    toParam: str


class PipelineRequest(BaseModel):
    """Pipeline definition with steps and auto-links."""

    steps: list[PipelineStepRequest]
    autoLinks: list[DataLinkRequest]


class StepPreview(BaseModel):
    """Preview of a single step."""

    order: int
    template_id: str
    template_name: str
    params: dict[str, str]


class ScriptPreviewResponse(BaseModel):
    """Merged multi-step script preview."""

    script: str
    steps: list[StepPreview]


class ExecutionTriggerResponse(BaseModel):
    """Execution trigger response."""

    execution_id: str
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_and_render_step(
    step: PipelineStepRequest,
) -> tuple[str, str, dict[str, str]]:
    """Validate a pipeline step and render its script.

    Args:
        step: Pipeline step request.

    Returns:
        (template_name, rendered_script_content, resolved_params) tuple.

    Raises:
        HTTPException: 400 if template not found or params invalid.
    """
    registry = get_registry()
    template = registry.get_template(step.template_id)
    if template is None:
        raise HTTPException(
            status_code=400,
            detail=f"Template not found: {step.template_id}",
        )

    engine = get_template_engine()
    ok, error = engine.validate_params_for_template(template, step.params)
    if not ok:
        raise HTTPException(status_code=400, detail=error)

    rendered = engine.render(template, step.params)
    return template.name, rendered.content, step.params


def _apply_auto_links(
    steps: list[PipelineStepRequest],
    auto_links: list[DataLinkRequest],
) -> list[PipelineStepRequest]:
    """Apply auto-link rules to pipeline steps.

    For each link, copies the value of ``fromParam`` from ``fromStep``
    to ``toParam`` of ``toStep``.

    Args:
        steps: Original pipeline steps.
        auto_links: Data link rules.

    Returns:
        Steps with auto-linked parameters applied.
    """
    # Create mutable copies of params
    step_params = [dict(s.params) for s in steps]

    for link in auto_links:
        from_idx = link.fromStep
        to_idx = link.toStep
        if 0 <= from_idx < len(step_params) and 0 <= to_idx < len(step_params):
            if link.fromParam in step_params[from_idx]:
                step_params[to_idx][link.toParam] = step_params[from_idx][
                    link.fromParam
                ]

    # Rebuild PipelineStepRequest instances
    return [
        PipelineStepRequest(
            order=s.order, template_id=s.template_id, params=step_params[i]
        )
        for i, s in enumerate(steps)
    ]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=ScriptPreviewResponse)
async def preview_pipeline(request: PipelineRequest) -> dict[str, Any]:
    """Preview a multi-step pipeline as a merged script.

    Validates each step's template and parameters, applies auto-links,
    renders each step's script, and merges them into a single output.

    Args:
        request: Pipeline definition.

    Returns:
        ScriptPreviewResponse with merged script and step details.

    Raises:
        HTTPException: 400 if any step is invalid.
    """
    steps = _apply_auto_links(request.steps, request.autoLinks)

    step_previews: list[StepPreview] = []
    script_parts: list[str] = []

    for step in steps:
        template_name, content, resolved_params = _validate_and_render_step(step)

        step_previews.append(
            StepPreview(
                order=step.order,
                template_id=step.template_id,
                template_name=template_name,
                params=resolved_params,
            )
        )
        script_parts.append(content.strip())

    merged_script = "\n\n".join(script_parts)

    return ScriptPreviewResponse(
        script=merged_script,
        steps=step_previews,
    ).model_dump()


@router.post("/execute", response_model=ExecutionTriggerResponse, status_code=202)
async def execute_pipeline(request: PipelineRequest) -> ExecutionTriggerResponse:
    """Trigger pipeline execution.

    Actual execution is handled via WebSocket (T-UX-05).
    This endpoint validates the pipeline and returns an execution ID.

    Args:
        request: Pipeline definition.

    Returns:
        ExecutionTriggerResponse with execution_id.
    """
    # Validate pipeline (same logic as preview)
    steps = _apply_auto_links(request.steps, request.autoLinks)
    for step in steps:
        _validate_and_render_step(step)

    return ExecutionTriggerResponse(
        execution_id=str(uuid.uuid4()),
        message="Pipeline execution triggered. Connect to WebSocket for live output.",
    )
