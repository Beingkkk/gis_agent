"""Generator REST API routes.

Provides endpoints for LLM-driven J2 template generation,
validation, and saving.

Design:
    T-UX-07 (DC-UX-07), plan-j2-generate DC-0092, DC-0093, DC-0094, DC-0095
"""

import logging
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from jinja2 import Environment, TemplateSyntaxError
from pydantic import BaseModel

from api.dependencies import get_llm_client, refresh_registry
from llm.template_generator import (
    auto_complete_params,
    generate_template_sync,
    parse_generated_response,
    sanitize_params,
)
from templates.engine import ScriptSecurityChecker
from templates.extractors import HtmlExtractor, MarkdownExtractor

router = APIRouter(prefix="/generator", tags=["generator"])

logger = logging.getLogger(__name__)

# Token budget for LLM template generation input.
# Claude supports 200K context; we reserve ~12000 for the user document
# plus system prompt and few-shot examples (~1500 tokens).
_MAX_INPUT_TOKENS = 12000


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: len(text) // 4."""
    return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class GenerateConfig(BaseModel):
    """Configuration for template generation."""

    category: str | None = None
    tool_source: str | None = None


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


class FileItem(BaseModel):
    """Single file item for multi-file parse request.

    Design:
        DC-0095
    """

    content: str
    file_type: str  # "html" | "markdown"


class ParseDocumentRequest(BaseModel):
    """Request to parse and clean documents for LLM input.

    Supports single file (legacy) or multi-file array.

    Design:
        DC-0088, DC-0095
    """

    files: list[FileItem]


class FileResult(BaseModel):
    """Per-file parse result."""

    file_type: str
    raw_chars: int
    cleaned_chars: int


class ParseDocumentResponse(BaseModel):
    """Cleaned document text ready for LLM consumption.

    Design:
        DC-0095
    """

    files: list[FileResult]
    document_text: str
    total_raw_chars: int
    total_cleaned_chars: int
    estimated_tokens: int


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


def _clean_file(content: str, file_type: str) -> str:
    """Clean a single file based on its type.

    Args:
        content: Raw file content.
        file_type: "html" or "markdown".

    Returns:
        Cleaned text.

    Raises:
        HTTPException: If file_type is unsupported.
    """
    ft = file_type.lower().strip()
    if ft in ("html", "htm"):
        extractor = HtmlExtractor()
        return extractor.extract(content)
    elif ft in ("markdown", "md"):
        return MarkdownExtractor.extract(content)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file_type: {file_type}. Use 'html' or 'markdown'.",
        )


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

    Uses the shared generation engine (DC-0094) with full system prompt,
    few-shot examples, robust JSON parsing, and retry logic.

    Args:
        request: Document text and generation config.

    Returns:
        GeneratedTemplateResponse with template body and metadata.

    Raises:
        HTTPException: 400 if input is empty, 413 if token budget exceeded,
            500 if generation fails.

    Design:
        DC-0094
    """
    document_text = request.document_text.strip()
    if not document_text:
        raise HTTPException(status_code=400, detail="document_text is required")

    # Token budget check (DC-0095)
    estimated_tokens = _estimate_tokens(document_text)
    if estimated_tokens > _MAX_INPUT_TOKENS:
        raise HTTPException(
            status_code=413,
            detail=(
                f"文档过长（约 {estimated_tokens} tokens），"
                f"请精简后重试（上限 {_MAX_INPUT_TOKENS} tokens）"
            ),
        )

    llm_client = get_llm_client()

    try:
        logger.info(
            "Generating template (doc_len=%d, category=%s)",
            len(document_text),
            request.config.category or "general",
        )
        data = generate_template_sync(
            client=llm_client,
            document_text=document_text,
            config=request.config.model_dump(),
        )
        body_raw = data.get("body") or data.get("command_template", "")
        tid_raw = data.get("template_id") or data.get("id", "N/A")
        logger.info(
            "Parsed response: template_id=%s name=%s body_len=%d",
            tid_raw,
            data.get("name", "N/A"),
            len(body_raw),
        )
    except ValueError as exc:
        logger.error("Failed to parse LLM response: %s", exc)
        raise HTTPException(
            status_code=500, detail=f"Invalid JSON from LLM: {exc}"
        ) from exc
    except Exception as exc:
        logger.exception("Template generation failed")
        raise HTTPException(
            status_code=500, detail=f"Generation failed: {exc}"
        ) from exc

    # Assemble full .j2 body from LLM structured output (DC-0094)
    # LLM prompt uses "command_template" and "id"; API model uses "body"
    # and "template_id". Accept both for backward compatibility.
    from llm.template_generator import assemble_j2_body

    params_raw = sanitize_params(data.get("params", []))
    body = data.get("body") or data.get("command_template", "")
    params_raw = auto_complete_params(body, params_raw)

    # Build the full .j2 file content (comment header + @echo off + command)
    data_with_params = dict(data)
    data_with_params["params"] = params_raw
    j2_body = assemble_j2_body(data_with_params)

    params = [
        ParamDefItem(
            name=p.get("name", ""),
            type=p.get("type", "string"),
            required=p.get("required", True),
        )
        for p in params_raw
    ]

    return GeneratedTemplateResponse(
        template_id=data.get("template_id")
        or data.get("id", "generated"),
        name=data.get("name", "Generated Template"),
        description=data.get("description", ""),
        body=j2_body,
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


@router.post("/parse-document", response_model=ParseDocumentResponse)
async def parse_document(request: ParseDocumentRequest) -> ParseDocumentResponse:
    """Parse and clean raw documents (HTML/Markdown) for LLM input.

    Supports multi-file input. Cleans each file and merges with ``---\n``
    separators. Returns per-file stats and total estimated token count.

    Token budget is NOT enforced here — the caller checks before sending
    to the LLM (DC-0095 v2).

    Args:
        request: List of files with content and type.

    Returns:
        ParseDocumentResponse with cleaned merged text and token estimate.

    Raises:
        HTTPException: 400 if files array is empty or contains unsupported type.

    Design:
        DC-0088, DC-0095
    """
    if not request.files:
        raise HTTPException(status_code=400, detail="files array is required")

    file_results: list[FileResult] = []
    cleaned_parts: list[str] = []
    total_raw = 0
    total_cleaned = 0

    for item in request.files:
        content = item.content
        file_type = item.file_type

        cleaned = _clean_file(content, file_type)
        file_results.append(
            FileResult(
                file_type=file_type,
                raw_chars=len(content),
                cleaned_chars=len(cleaned),
            )
        )
        cleaned_parts.append(cleaned)
        total_raw += len(content)
        total_cleaned += len(cleaned)

    # Merge with separators
    merged_text = "\n---\n".join(cleaned_parts)
    estimated_tokens = _estimate_tokens(merged_text)

    logger.info(
        "Parsed %d documents (total_raw=%d, total_cleaned=%d, tokens=%d)",
        len(request.files),
        total_raw,
        total_cleaned,
        estimated_tokens,
    )

    return ParseDocumentResponse(
        files=file_results,
        document_text=merged_text,
        total_raw_chars=total_raw,
        total_cleaned_chars=total_cleaned,
        estimated_tokens=estimated_tokens,
    )
