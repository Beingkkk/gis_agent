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

Checklist:
1. `id` format: must match `^[a-z0-9_]+$` and be descriptive
2. `command_template` Jinja2 syntax: must be valid Jinja2, no syntax errors
3. `command_template` variable consistency: every {{ var }} and {% if var %} must correspond to a declared param name
4. `command_template` security: path/string params must use `| quote` filter
5. Param type correctness: `-s_srs`/`-t_srs`/`-a_srs` should be `crs`, file paths should be `file_path`, flags should be `boolean`
6. Required params: `required: true` params must not have `default`
7. `common_errors`: must be extracted from actual documentation, not invented
8. Command safety: no dangerous shell patterns (`;`, `|`, `$()`, `&&`)

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
        "command_template": template_def.command_template,
        "params": [
            {
                "name": p.name,
                "type": p.type,
                "required": p.required,
                "description": p.description,
                "default": p.default,
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
    """Parse LLM review JSON output."""
    cleaned = _strip_markdown_json(raw)
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

        if strict and result.issues:
            # Any issue in strict mode = not passed
            return ReviewResult(
                passed=False,
                issues=result.issues,
                suggested_fix=result.suggested_fix,
            )

        return result
