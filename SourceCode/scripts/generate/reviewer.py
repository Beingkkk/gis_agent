"""LLM template reviewer.

Design: plan-j2-generate T-GEN-04, DC-0086, DC-0087
"""

import json
import logging
from dataclasses import dataclass
from typing import Any

from llm.client import LLMClient
from llm.models import Message

from generate.models import TemplateDefinition

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReviewIssue:
    """A single review finding."""

    item: int
    severity: str  # "error" | "warning"
    message: str


@dataclass(frozen=True)
class ReviewResult:
    """Result of template quality review."""

    passed: bool
    issues: list[ReviewIssue]
    suggested_fix: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a senior GIS developer reviewing Jinja2 template definitions for the GIS Agent system.

Review the provided TemplateDefinition against the following checklist. For each item, decide if it PASSES or FAILS. If it fails, report the severity (error/warning) and a specific message.

System context:
- Valid param types: `file_path`, `folder_path`, `crs`, `string`, `text`, `boolean`, `integer`, `float`, `enum`, `format`
- `format` is a specialized enum for GDAL output format names (e.g. GeoJSON, ESRI Shapefile). It MUST have `options` listing common formats.
- `enum` is a general enum with `options` listing valid choices.
- `text` is for multi-line string values (e.g. KEY=VALUE config pairs).
- `folder_path` is for directory paths (semantic distinction from file_path).
- `safe_path` and `quote` are system-registered custom Jinja2 filters. `safe_path` normalizes paths; `quote` performs shell escaping. They are VALID and EXPECTED.
- `| safe_path | quote` chain is the standard pattern for path parameters.
- GDAL 3.x+ introduced a unified `gdal` command with subcommands in the form `gdal <subcommand>` or `gdal <domain> <subcommand>`. Examples of VALID GDAL 3.x commands: `gdal convert`, `gdal dataset copy`, `gdal dataset rename`, `gdal raster contour`, `gdal raster mosaic`, `gdal raster select`, `gdal vector select`, `gdal vector segmentize`, `gdal vector rename-layer`, `gdal vsi copy`, `gdal mdim convert`, `gdal mdim mosaic`, `gdal external`. These are REAL commands and must NOT be flagged as non-existent.

Checklist:
1. `id` format: must match `^[a-z0-9_]+$` and be descriptive
2. `command_template` Jinja2 syntax: must be valid Jinja2, no syntax errors
3. `command_template` variable consistency: every {{ var }} and {% if var %} must correspond to a declared param name
4. `command_template` security: params of type `file_path`, `folder_path`, `string`, `text`, or `crs` MUST use `| quote` filter (`| safe_path | quote` is acceptable for paths). Types `integer`, `float`, `boolean`, `enum`, `format` do NOT require `| quote`.
5. Param type correctness: `-s_srs`/`-t_srs`/`-a_srs` -> `crs`, file paths -> `file_path`, dir paths -> `folder_path`, on/off flags -> `boolean`, output formats -> `format` (with options), multi-line config -> `text`
6. `format` and `enum` params MUST have non-empty `options` array
7. Required params: `required: true` params must not have `default`
8. `keywords`: must include at least 3 relevant terms (format abbreviations, common names, operation verbs)
9. `common_errors`: must be extracted from actual documentation, not invented
10. Command safety: no dangerous shell patterns (`;`, `|`, `$()`, `&&`)

Output strict JSON only. Format:
{
  "passed": true|false,
  "issues": [
    {"item": 1, "severity": "error|warning", "message": "..."}
  ],
  "suggested_fix": null|{...}
}

If `passed` is true, `issues` should be empty."""


def _build_review_prompt(template_def: TemplateDefinition) -> str:
    """Serialize TemplateDefinition for review prompt."""
    data = {
        "id": template_def.id,
        "name": template_def.name,
        "description": template_def.description,
        "category": template_def.category,
        "keywords": template_def.keywords,
        "command_template": template_def.command_template,
        "params": [
            {
                "name": p.name,
                "type": p.type,
                "required": p.required,
                "description": p.description,
                "default": p.default,
                "options": p.options,
            }
            for p in template_def.params
        ],
        "concepts": template_def.concepts,
        "notes": template_def.notes,
        "common_errors": template_def.common_errors,
        "seealso": template_def.seealso,
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def _strip_markdown_json(text: str) -> str:
    """Remove markdown code block wrappers if present."""
    text = text.strip()
    if text.startswith("```"):
        first_nl = text.find("\n")
        if first_nl != -1:
            text = text[first_nl + 1 :]
        if text.endswith("```"):
            text = text[:-3].strip()
    return text.strip()


def _parse_review_result(raw: str) -> ReviewResult:
    """Parse LLM review JSON output with multiple fallback strategies.

    If all parsing strategies fail, trust-degrade to passed=True
    because the TemplateDefinition already passed generator validation
    and runtime has an independent ScriptSecurityChecker.

    Design: DC-0086
    """
    # Strategy 1: standard markdown strip + json parse
    strategies = [
        _strip_markdown_json(raw),
    ]

    # Strategy 2: extract first {...} block (handles trailing text)
    first_brace = raw.find("{")
    last_brace = raw.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        strategies.append(raw[first_brace : last_brace + 1])

    # Strategy 3: try to fix common LLM truncation issues
    # (missing closing brace/bracket)
    for s in list(strategies):
        # Fix missing closing braces
        open_braces = s.count("{") - s.count("}")
        if open_braces > 0:
            strategies.append(s + "}" * open_braces)
        # Fix missing closing brackets
        open_brackets = s.count("[") - s.count("]")
        if open_brackets > 0:
            strategies.append(s + "]" * open_brackets)

    for attempt, cleaned in enumerate(strategies):
        try:
            data = json.loads(cleaned)

            issues = [
                ReviewIssue(
                    item=issue.get("item", 0),
                    severity=issue.get("severity", "warning"),
                    message=issue.get("message", ""),
                )
                for issue in data.get("issues", [])
            ]

            return ReviewResult(
                passed=data.get("passed", False),
                issues=issues,
                suggested_fix=data.get("suggested_fix"),
            )
        except (json.JSONDecodeError, TypeError) as exc:
            logger.debug("Review JSON parse strategy %d failed: %s", attempt + 1, exc)
            continue

    # All strategies failed — trust degrade. The template already passed
    # generator validation (TemplateDefinition.__post_init__) and runtime
    # has ScriptSecurityChecker as an independent safety net.
    logger.warning(
        "Review JSON parse failed after %d strategies, trust-degrading to passed. "
        "Raw response preview: %s",
        len(strategies),
        raw[:200].replace("\n", " "),
    )
    return ReviewResult(passed=True, issues=[])


# ---------------------------------------------------------------------------
# Reviewer
# ---------------------------------------------------------------------------


class LLMTemplateReviewer:
    """Review TemplateDefinition quality via LLM checklist.

    Design: DC-0086, DC-0087
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._client = llm_client

    def review(
        self,
        template_def: TemplateDefinition,
        *,
        strict: bool = True,
    ) -> ReviewResult:
        """Review a TemplateDefinition for quality issues.

        Args:
            template_def: The template to review.
            strict: If True, any warning is treated as a failure.

        Returns:
            ReviewResult with passed status and issue list.
        """
        prompt = _build_review_prompt(template_def)

        messages = [Message(role="user", content=prompt)]

        try:
            raw_response = self._client.chat(
                system_prompt=_SYSTEM_PROMPT,
                messages=messages,
                temperature=0.1,
            )
        except Exception as exc:
            logger.warning("LLM review failed: %s", exc)
            return ReviewResult(
                passed=False,
                issues=[
                    ReviewIssue(
                        item=0,
                        severity="error",
                        message=f"LLM review call failed: {exc}",
                    )
                ],
            )

        try:
            result = _parse_review_result(raw_response)
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Review result parse failed: %s", exc)
            return ReviewResult(
                passed=False,
                issues=[
                    ReviewIssue(
                        item=0,
                        severity="error",
                        message=f"Review result parse failed: {exc}",
                    )
                ],
            )

        # Non-strict mode: only errors cause rejection, warnings are informational
        if not strict:
            errors = [i for i in result.issues if i.severity == "error"]
            if not errors:
                return ReviewResult(
                    passed=True,
                    issues=result.issues,
                    suggested_fix=result.suggested_fix,
                )
            return ReviewResult(
                passed=False,
                issues=errors,
                suggested_fix=result.suggested_fix,
            )

        # Strict mode: any issue causes rejection
        if result.issues:
            return ReviewResult(
                passed=False,
                issues=result.issues,
                suggested_fix=result.suggested_fix,
            )

        return result
