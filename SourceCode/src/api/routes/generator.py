"""Generator REST API routes.

Provides endpoints for LLM-driven J2 template generation,
validation, and saving.

Design:
    T-UX-07 (DC-UX-07)
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from jinja2 import Environment, TemplateSyntaxError
from pydantic import BaseModel

from api.dependencies import get_llm_client
from templates.engine import ScriptSecurityChecker

router = APIRouter(prefix="/generator", tags=["generator"])

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class GenerateConfig(BaseModel):
    """Configuration for template generation."""

    category: Optional[str] = None
    tool_source: Optional[str] = None


class GenerateRequest(BaseModel):
    """Request to generate a template from documentation."""

    document_text: str
    config: GenerateConfig


class ParamDefItem(BaseModel):
    """Generated parameter definition."""

    name: str
    type: str
    required: bool


class GeneratedTemplateResponse(BaseModel):
    """LLM-generated template result."""

    template_id: str
    name: str
    description: str
    body: str
    params: list[ParamDefItem]
    concepts: list[str]
    notes: list[str]


class ValidateRequest(BaseModel):
    """Request to validate a template body."""

    body: str


class ValidationResultResponse(BaseModel):
    """Template validation result."""

    valid: bool
    errors: list[str]


class SaveRequest(BaseModel):
    """Request to save a generated template."""

    template_id: str
    body: str
    overwrite: bool = False


class SaveResponse(BaseModel):
    """Template save result."""

    saved_path: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_templates_dir() -> Path:
    """Resolve the templates directory path.

    Returns:
        Path to data/templates/ relative to project root.
    """
    # api/routes/generator.py -> api/routes -> api -> src -> SourceCode
    return Path(__file__).parent.parent.parent.parent / "data" / "templates"


def _build_generate_prompt(document_text: str, config: GenerateConfig) -> str:
    """Build LLM prompt for template generation.

    Args:
        document_text: GDAL documentation text.
        config: Generation configuration.

    Returns:
        System prompt for LLM.
    """
    category = config.category or "general"
    tool_source = config.tool_source or "GDAL"

    return (
        f"You are a Jinja2 template generator for GIS tools.\n"
        f"Generate a Jinja2 template definition based on the following "
        f"GDAL {tool_source} documentation.\n"
        f"Category: {category}\n\n"
        f"Return ONLY a JSON object with these fields:\n"
        f'  "template_id": string (kebab-case ID)\n'
        f'  "name": string (human-readable Chinese name)\n'
        f'  "description": string (one-line description)\n'
        f'  "body": string (full Jinja2 template with comment header)\n'
        f'  "params": array of {{"name", "type", "required"}}\n'
        f'  "concepts": array of strings\n'
        f'  "notes": array of strings\n\n'
        f"Documentation:\n{document_text}\n"
    )


def _parse_generated_response(text: str) -> dict[str, Any]:
    """Parse LLM response into a dict.

    Strips markdown code fences if present.

    Args:
        text: Raw LLM response text.

    Returns:
        Parsed dict.

    Raises:
        ValueError: If JSON parsing fails.
    """
    stripped = text.strip()
    # Strip markdown ```json ... ``` fences
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        # Remove first line (```json) and last line (```)
        if len(lines) > 2:
            stripped = "\n".join(lines[1:-1]).strip()

    return json.loads(stripped)


def _validate_jinja2_syntax(body: str) -> tuple[bool, list[str]]:
    """Validate Jinja2 template syntax.

    Args:
        body: Template body string.

    Returns:
        (is_valid, error_messages).
    """
    env = Environment()
    try:
        env.parse(body)
        return True, []
    except TemplateSyntaxError as exc:
        return False, [f"Jinja2 syntax error at line {exc.lineno}: {exc.message}"]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/generate", response_model=GeneratedTemplateResponse)
async def generate_template(request: GenerateRequest) -> dict[str, Any]:
    """Generate a J2 template from GDAL documentation text.

    Args:
        request: Document text and generation config.

    Returns:
        GeneratedTemplateResponse with template body and metadata.

    Raises:
        HTTPException: 400 if input is empty, 500 if generation fails.
    """
    document_text = request.document_text.strip()
    if not document_text:
        raise HTTPException(status_code=400, detail="document_text is required")

    llm_client = get_llm_client()
    system_prompt = _build_generate_prompt(document_text, request.config)

    try:
        from llm.models import Message

        response_text = llm_client.chat(
            system_prompt=system_prompt,
            messages=[Message(role="user", content=document_text)],
        )
        data = _parse_generated_response(response_text)
    except json.JSONDecodeError as exc:
        logger.exception("Failed to parse LLM response as JSON")
        raise HTTPException(
            status_code=500, detail=f"Invalid JSON from LLM: {exc}"
        ) from exc
    except Exception as exc:
        logger.exception("Template generation failed")
        raise HTTPException(
            status_code=500, detail=f"Generation failed: {exc}"
        ) from exc

    params = [
        ParamDefItem(
            name=p.get("name", ""),
            type=p.get("type", "string"),
            required=p.get("required", True),
        )
        for p in data.get("params", [])
    ]

    return GeneratedTemplateResponse(
        template_id=data.get("template_id", "generated"),
        name=data.get("name", "Generated Template"),
        description=data.get("description", ""),
        body=data.get("body", ""),
        params=params,
        concepts=data.get("concepts", []),
        notes=data.get("notes", []),
    ).model_dump()


@router.post("/validate", response_model=ValidationResultResponse)
async def validate_template(request: ValidateRequest) -> ValidationResultResponse:
    """Validate a template body for security and syntax.

    Args:
        request: Template body to validate.

    Returns:
        ValidationResultResponse with valid flag and any errors.
    """
    errors: list[str] = []

    # Security check
    checker = ScriptSecurityChecker()
    safe, reason = checker.check(request.body)
    if not safe:
        errors.append(f"Security check failed: {reason}")

    # Jinja2 syntax check
    valid, syntax_errors = _validate_jinja2_syntax(request.body)
    if not valid:
        errors.extend(syntax_errors)

    return ValidationResultResponse(valid=len(errors) == 0, errors=errors)


@router.post("/save", response_model=SaveResponse)
async def save_template(request: SaveRequest) -> SaveResponse:
    """Save a generated template to the templates directory.

    Args:
        request: Template ID, body, and overwrite flag.

    Returns:
        SaveResponse with the saved file path.

    Raises:
        HTTPException: 409 if file exists and overwrite is False.
    """
    template_dir = _get_templates_dir()
    template_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{request.template_id}.j2"
    file_path = template_dir / filename

    if file_path.exists() and not request.overwrite:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Template already exists: {filename}."
                " Use overwrite=true to replace."
            ),
        )

    file_path.write_text(request.body, encoding="utf-8")
    logger.info("Template saved to %s", file_path)

    return SaveResponse(saved_path=str(file_path))
