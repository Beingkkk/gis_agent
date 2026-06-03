"""LLM template generator.

Design: plan-j2-generate T-GEN-03, DC-0085, DC-0094
"""

import logging
from typing import Any

from llm.client import LLMClient
from llm.models import Message
from llm.template_generator import (
    FEW_SHOT_EXAMPLES,
    SYSTEM_PROMPT,
    auto_complete_params,
    parse_generated_response,
    sanitize_params,
)

from generate.models import ExtractedDoc, ParamDef, TemplateDefinition

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_doc_text(extracted: ExtractedDoc) -> str:
    """Build the user message content from extracted document."""
    lines = [
        f"GDAL Tool: {extracted.title}",
        "",
        "SYNOPSIS:",
        extracted.synopsis if extracted.synopsis else "(not found)",
        "",
        "DESCRIPTION:",
        extracted.description if extracted.description else "(not found)",
    ]
    return "\n".join(lines)


def _parse_param(data: dict[str, Any]) -> ParamDef:
    """Parse a param dict into ParamDef."""
    return ParamDef(
        name=data["name"],
        type=data["type"],
        required=data.get("required", False),
        description=data.get("description", ""),
        default=data.get("default"),
        options=data.get("options", []),
    )


def _parse_template_def(raw_json: str) -> TemplateDefinition:
    """Parse LLM JSON output into TemplateDefinition.

    Uses the shared parsing logic from llm.template_generator (DC-0094)
    and adapts the result to CLI's TemplateDefinition dataclass.
    """
    data = parse_generated_response(raw_json)

    params_raw = data.get("params") or []
    params = [_parse_param(p) for p in params_raw if p is not None]

    # Sanitize using shared logic (convert ParamDef -> dict -> ParamDef)
    params_dicts = sanitize_params([{"name": p.name, "type": p.type, "required": p.required, "description": p.description, "default": p.default, "options": p.options} for p in params])
    params = [_parse_param(d) for d in params_dicts]

    command_template = data["command_template"]

    # Auto-complete undeclared template variables as optional boolean params
    param_names = {p.name for p in params}
    from llm.template_generator import _extract_template_vars

    undeclared = _extract_template_vars(command_template) - param_names
    if undeclared:
        logger.info(
            "Auto-completing %d undeclared params: %s",
            len(undeclared),
            sorted(undeclared),
        )
        for name in sorted(undeclared):
            params.append(
                ParamDef(
                    name=name,
                    type="boolean",
                    required=False,
                    description="(auto-completed)",
                )
            )

    return TemplateDefinition(
        id=data["id"],
        name=data["name"],
        description=data["description"],
        category=data["category"],
        command_template=command_template,
        params=params,
        concepts=data.get("concepts", []),
        notes=data.get("notes", []),
        common_errors=data.get("common_errors", []),
        seealso=data.get("seealso", []),
        keywords=data.get("keywords", []),
    )


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class LLMTemplateGenerator:
    """Generate TemplateDefinition from extracted documentation via LLM.

    Design: DC-0085, DC-0094
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._client = llm_client

    def generate(
        self, extracted: ExtractedDoc
    ) -> tuple[TemplateDefinition | None, str]:
        """Generate a TemplateDefinition from extracted document text.

        Args:
            extracted: Extracted document content.

        Returns:
            Tuple of (TemplateDefinition if successful, error_reason string).
            On success error_reason is empty.
        """
        doc_text = _build_doc_text(extracted)

        messages = [
            Message(role="user", content=FEW_SHOT_EXAMPLES),
            Message(
                role="assistant",
                content="Understood. I will analyze the provided GDAL documentation and generate a Jinja2 template definition in valid JSON format.",
            ),
            Message(role="user", content=doc_text),
        ]

        # Attempt 1: generate
        raw_response, gen_error = self._try_generate(messages, temperature=0.1)
        if raw_response is None:
            return None, gen_error

        # Attempt 1: parse
        template_def = self._try_parse(raw_response)
        if template_def is not None:
            return template_def, ""

        # Attempt 2: retry with slightly higher temperature + hint
        logger.info("Generation parse failed, retrying with adjusted prompt...")
        retry_messages = messages + [
            Message(role="assistant", content=raw_response),
            Message(
                role="user",
                content="Your previous response could not be parsed as valid JSON. "
                "Please output ONLY valid JSON, no markdown code blocks, no extra text.",
            ),
        ]
        raw_response2, gen_error2 = self._try_generate(
            retry_messages, temperature=0.2
        )
        if raw_response2 is None:
            return None, f"Retry generation failed: {gen_error2}"

        template_def2 = self._try_parse(raw_response2)
        if template_def2 is not None:
            return template_def2, ""

        return None, "JSON parse failed after retry"

    def _try_generate(
        self, messages: list[Message], temperature: float
    ) -> tuple[str | None, str]:
        """Single LLM generation attempt."""
        try:
            raw_response = self._client.chat(
                system_prompt=SYSTEM_PROMPT,
                messages=messages,
                temperature=temperature,
            )
        except Exception as exc:
            logger.warning("LLM generation failed: %s", exc)
            return None, f"LLM call failed: {exc}"
        return raw_response, ""

    def _try_parse(self, raw_response: str) -> TemplateDefinition | None:
        """Parse raw LLM response into TemplateDefinition.

        Returns None on any parse/validation error.
        """
        try:
            return _parse_template_def(raw_response)
        except Exception as exc:
            logger.debug("Template parse failed: %s", exc)
            return None