"""Template REST API routes.

Provides read-only endpoints for browsing templates:
list all templates and get detailed template information.

Design:
    T-UX-03 (DC-UX-02)
"""

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.dependencies import get_registry
from core.models import TemplateDef

router = APIRouter(prefix="/templates", tags=["templates"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class ParamDefResponse(BaseModel):
    """Parameter definition for API response."""

    name: str
    type: str
    required: bool
    description: str
    default: Optional[str] = None


class ConceptItemResponse(BaseModel):
    """Concept term explanation."""

    term: str
    explanation: str


class CommonErrorItemResponse(BaseModel):
    """Common error and fix suggestion."""

    error_text: str
    fix: str


class TemplateDefResponse(BaseModel):
    """Template summary for listing."""

    id: str
    name: str
    description: str
    category: str
    tool_source: str
    tags: list[str]


class TemplateDetailResponse(BaseModel):
    """Full template detail including params and knowledge metadata."""

    id: str
    name: str
    description: str
    category: str
    tool_source: str
    tags: list[str]
    params: list[ParamDefResponse]
    concepts: list[ConceptItemResponse]
    notes: list[str]
    common_errors: list[CommonErrorItemResponse]
    seealso: list[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _infer_category(template_file: str) -> str:
    """Infer template category from its file path.

    The template_file is stored as a relative path like
    ``vector/shp2geojson.j2`` or ``raster/convert.j2``.
    The first path segment is used as the category.

    Args:
        template_file: Relative path from template directory.

    Returns:
        Category string: ``vector``, ``raster``, ``general``, etc.
        Falls back to ``"general"`` if path has no directory segment.
    """
    if "/" in template_file:
        return template_file.split("/", 1)[0]
    return "general"


def _build_template_def_response(template: TemplateDef) -> dict[str, Any]:
    """Build template summary dict from TemplateDef.

    Args:
        template: Core TemplateDef instance.

    Returns:
        Dict matching TemplateDefResponse schema.
    """
    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "category": _infer_category(template.template_file),
        "tool_source": "GDAL",
        "tags": [],
    }


def _build_template_detail_response(template: TemplateDef) -> TemplateDetailResponse:
    """Build full TemplateDetailResponse from TemplateDef.

    Args:
        template: Core TemplateDef instance.

    Returns:
        TemplateDetailResponse for JSON serialization.
    """
    category = _infer_category(template.template_file)

    params = [
        ParamDefResponse(
            name=p.name,
            type=p.type,
            required=p.required,
            description=p.description,
            default=p.default,
        )
        for p in template.params
    ]

    concepts = [
        ConceptItemResponse(term=term, explanation=exp)
        for term, exp in template.concepts
    ]

    common_errors = [
        CommonErrorItemResponse(error_text=text, fix=fix)
        for text, fix in template.common_errors
    ]

    return TemplateDetailResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        category=category,
        tool_source="GDAL",
        tags=[],
        params=params,
        concepts=concepts,
        notes=list(template.notes),
        common_errors=common_errors,
        seealso=list(template.seealso),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[TemplateDefResponse])
async def list_templates() -> list[dict[str, Any]]:
    """List all available templates.

    Returns:
        List of template summaries sorted by id.
    """
    registry = get_registry()
    templates = registry.list_templates()
    return [_build_template_def_response(t) for t in templates]


@router.get("/{template_id}", response_model=TemplateDetailResponse)
async def get_template(template_id: str) -> TemplateDetailResponse:
    """Get detailed information for a specific template.

    Args:
        template_id: Template unique identifier.

    Returns:
        TemplateDetailResponse with params, concepts, notes, etc.

    Raises:
        HTTPException: 404 if template not found.
    """
    registry = get_registry()
    template = registry.get_template(template_id)
    if template is None:
        raise HTTPException(
            status_code=404, detail=f"Template not found: {template_id}"
        )
    return _build_template_detail_response(template)
