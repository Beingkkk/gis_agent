"""Generator REST API routes.

Provides endpoints for LLM-driven J2 template generation,
validation, and saving.

Design:
    T-UX-07 (DC-UX-07), plan-j2-generate DC-0092, DC-0093
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from jinja2 import Environment, TemplateSyntaxError
from pydantic import BaseModel

from api.dependencies import get_llm_client, refresh_registry
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
    category: str
    template_id: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Regex to extract @category from Jinja2 comment header
_CATEGORY_RE = re.compile(r"\{\#\s*@category\s+(\S+)\s*\#\}")
"""Match ``{# @category vector #}`` and capture the category name."""


def _get_templates_dir() -> Path:
    """Resolve the templates directory path.

    Returns:
        Path to data/templates/ relative to project root.
    """
    # api/routes/generator.py -> api/routes -> api -> src -> SourceCode
    return Path(__file__).parent.parent.parent.parent / "data" / "templates"


def _extract_category(body: str) -> str:
    """Extract @category from template body comment header.

    Searches the first 20 lines for ``{# @category name #}``.
    Falls back to ``"general"`` if not found.

    Args:
        body: Full J2 template body.

    Returns:
        Category string, normalized to lowercase.
    """
    for line in body.splitlines()[:20]:
        match = _CATEGORY_RE.search(line)
        if match:
            return match.group(1).strip().lower()
    return "general"


def _build_generate_prompt(config: GenerateConfig) -> str:
    """Build LLM system prompt for template generation.

    The system prompt contains only instructions and format specification.
    The actual documentation text is passed as a user message so the
    LLMClient truncation logic can manage its length.

    Args:
        config: Generation configuration.

    Returns:
        System prompt for LLM.
    """
    category = config.category or "general"
    tool_source = config.tool_source or "GDAL"

    return (
        f"You are a Jinja2 template generator for GIS tools.\n"
        f"Generate a Jinja2 template definition based on the "
        f"GDAL {tool_source} documentation provided by the user.\n"
        f"Category: {category}\n\n"
        f"Return ONLY a JSON object with these fields:\n"
        f'  "template_id": string (kebab-case ID)\n'
        f'  "name": string (human-readable Chinese name)\n'
        f'  "description": string (one-line description)\n'
        f'  "body": string (full Jinja2 template with comment header)\n'
        f'  "params": array of {{"name", "type", "required"}}\n'
        f'  "concepts": array of strings\n'
        f'  "notes": array of strings\n'
    )


def _parse_generated_response(text: str) -> dict[str, Any]:
    """Parse LLM response into a dict.

    Handles several common LLM output patterns:
    - Pure JSON
    - Markdown `` ```json ... ``` `` fences
    - Markdown `` ``` ... ``` `` fences (no language tag)
    - Explanatory text followed by a fenced JSON block
    - JSON embedded in explanatory text (extracts first ``{...}``)

    Args:
        text: Raw LLM response text.

    Returns:
        Parsed dict.

    Raises:
        ValueError: If JSON parsing fails.
    """
    stripped = text.strip()

    # Pattern 1: markdown code fence (with or without language tag)
    fence_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", stripped, re.DOTALL)
    if fence_match:
        candidate = fence_match.group(1).strip()
        try:
            return json.loads(candidate)  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            pass  # Fall through to broader extraction

    # Pattern 2: find the first top-level JSON object {...}
    brace_match = re.search(r"(\{.*\})", stripped, re.DOTALL)
    if brace_match:
        candidate = brace_match.group(1).strip()
        try:
            return json.loads(candidate)  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            pass

    # Pattern 3: try the whole text as JSON (last resort)
    return json.loads(stripped)  # type: ignore[no-any-return]


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
    system_prompt = _build_generate_prompt(request.config)

    try:
        from llm.models import Message

        logger.info(
            "Generating template (doc_len=%d, category=%s)",
            len(document_text),
            request.config.category or "general",
        )
        response_text = llm_client.chat(
            system_prompt=system_prompt,
            messages=[Message(role="user", content=document_text)],
        )
        logger.debug("LLM raw response length=%d", len(response_text))
        data = _parse_generated_response(response_text)
        logger.info(
            "Parsed response: template_id=%s name=%s body_len=%d",
            data.get("template_id", "N/A"),
            data.get("name", "N/A"),
            len(data.get("body", "")),
        )
    except json.JSONDecodeError as exc:
        logger.error(
            "Failed to parse LLM response as JSON. Raw prefix: %s",
            response_text[:500] if "response_text" in dir() else "N/A",
        )
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

    Extracts category from the template body comment header and saves
    to ``data/templates/{category}/{template_id}.j2``. After saving,
    triggers registry rescan so the new template is immediately available.

    Args:
        request: Template ID, body, and overwrite flag.

    Returns:
        SaveResponse with the saved file path, category, and template ID.

    Raises:
        HTTPException: 409 if file exists and overwrite is False.

    Design:
        plan-j2-generate DC-0092, DC-0093
    """
    template_dir = _get_templates_dir()
    category = _extract_category(request.body)

    # Save to category subdirectory (DC-0092)
    category_dir = template_dir / category
    category_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{request.template_id}.j2"
    file_path = category_dir / filename

    if file_path.exists() and not request.overwrite:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Template already exists: {category}/{filename}."
                " Use overwrite=true to replace."
            ),
        )

    file_path.write_text(request.body, encoding="utf-8")
    logger.info("Template saved to %s (category=%s)", file_path, category)

    # Trigger registry rescan so the new template is immediately available (DC-0093)
    try:
        new_count = refresh_registry()
        logger.info("Registry rescanned: %d templates total", new_count)
    except Exception:
        logger.exception("Registry rescan failed after save")
        # Don't fail the save if rescan fails; the template is on disk

    return SaveResponse(
        saved_path=str(file_path),
        category=category,
        template_id=request.template_id,
    )
