"""Jinja2 template engine for GDAL script generation.

Design: plan-templates v1.0.0 (DC-0050 ~ DC-0054)
"""

import re
import shlex
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from jinja2 import Environment, FileSystemLoader

from core.models import TemplateDef
from core.workspace import Workspace


class Platform(Enum):
    """Target platform for script output.

    Design:
        DC-0054
    """

    WINDOWS = "windows"
    UNIX = "unix"


@dataclass(frozen=True)
class RenderedScript:
    """Rendered script output.

    Design:
        DC-0054
    """

    content: str
    command_lines: List[str]
    platform: Platform
    output_path: str


class TemplateError(Exception):
    """Base exception for template module."""


class TemplateNotFoundError(TemplateError):
    """Template file does not exist.

    Design:
        DC-0050
    """


class RenderError(TemplateError):
    """Template rendering failed.

    Design:
        DC-0051, DC-0053
    """


class SecurityCheckError(TemplateError):
    """Rendered script failed security check.

    Design:
        DC-0052
    """


# Whitelist: letters, digits, underscore, dot, slash, colon, at, hyphen,
# equals, double-quote, whitespace.
_WHITELIST_RE = re.compile(r'^[\w\./:@\-="\s]+$', re.UNICODE)


def quote_filter(value: str) -> str:
    """Shell-safe quoting filter using shlex.quote.

    Wraps the value in shell-safe quotes to prevent word splitting
    and metacharacter expansion.

    Design:
        DC-0051, DC-0053
    """
    return shlex.quote(value)


def safe_path_filter(value: str, workspace: Workspace) -> str:
    """Resolve path via workspace and return as string.

    Relative paths are resolved against the workspace root.
    Absolute paths are passed through without restriction
    (workspace v2.0.0 is a memory anchor, not a security boundary).

    Design:
        DC-0053, DC-0051, DC-0011
    """
    resolved = workspace.resolve_path(value)
    return str(resolved)


class ScriptSecurityChecker:
    """Post-render script security validator.

    Checks rendered command strings for dangerous patterns that could
    indicate command injection or path traversal.

    Design:
        DC-0052
    """

    DANGEROUS_PATTERNS: List[Tuple[str, str]] = [
        (r"[;&|]", "contains command separator"),
        (r"\$\(", "contains command substitution"),
        (r"`", "contains backtick command substitution"),
        (r"[<>]{2,}", "contains abnormal redirection"),
        (r"\.\./\.\.", "contains path traversal"),
    ]

    def check(self, script: str) -> Tuple[bool, Optional[str]]:
        """Check if script contains dangerous patterns.

        Args:
            script: Rendered script content.

        Returns:
            (True, None) if safe.
            (False, reason) if unsafe, where reason describes the issue.
        """
        for pattern, reason in self.DANGEROUS_PATTERNS:
            if re.search(pattern, script):
                return (False, reason)
        return (True, None)


class TemplateEngine:
    """Jinja2 template rendering engine.

    Manages Jinja2 environment, custom filters, parameter validation,
    template rendering, and post-render security checks.

    Design:
        DC-0050, DC-0051, DC-0052, DC-0053, DC-0054
    """

    def __init__(
        self,
        template_dir: Path,
        workspace: Workspace,
    ) -> None:
        """Initialize Jinja2 environment.

        Args:
            template_dir: Root directory for .j2 template files.
            workspace: For safe_path resolution.
        """
        self._workspace = workspace
        self._env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=False,  # GDAL scripts are not HTML
        )
        # Register custom filters
        self._env.filters["quote"] = quote_filter
        self._env.filters["safe_path"] = lambda value: safe_path_filter(
            value, self._workspace
        )

    def render(
        self,
        template_def: TemplateDef,
        params: Dict[str, str],
        platform: Optional[Platform] = None,
    ) -> RenderedScript:
        """Render template into executable script.

        Execution flow:
        1. Pre-validate parameters (required + whitelist).
        2. Load Jinja2 template file.
        3. Render with custom filters applied.
        4. Extract GDAL command lines.
        5. Run secondary security check.
        6. Assemble RenderedScript result.

        Args:
            template_def: Template definition from registry.
            params: Parameter key-value pairs.
            platform: Target platform. Defaults to current OS.

        Returns:
            Rendered script with metadata.

        Raises:
            RenderError: Parameter validation or rendering failure.
            TemplateNotFoundError: Template file missing.
            SecurityCheckError: Rendered content contains dangerous patterns.

        Design:
            DC-0050 ~ DC-0054
        """
        # 1. Pre-validate parameters
        ok, error = self.validate_params_for_template(template_def, params)
        if not ok:
            raise RenderError(error)

        # 2. Load Jinja2 template
        template_path = template_def.template_file
        try:
            template = self._env.get_template(template_path)
        except Exception as exc:
            raise TemplateNotFoundError(f"Template not found: {template_path}") from exc

        # 3. Render
        try:
            raw = template.render(**params)
        except Exception as exc:
            raise RenderError(f"Template rendering failed: {exc}") from exc

        # 4. Extract GDAL command lines
        # Skip comment lines, batch headers, empty lines
        command_lines: List[str] = []
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(("#", "@", "REM")):
                continue
            command_lines.append(stripped)

        # 5. Secondary security check
        checker = ScriptSecurityChecker()
        ok, reason = checker.check(raw)
        if not ok:
            raise SecurityCheckError(f"Security check failed: {reason}")

        # 6. Determine platform and output path
        if platform is None:
            platform = Platform.WINDOWS if sys.platform == "win32" else Platform.UNIX

        ext = ".bat" if platform == Platform.WINDOWS else ".sh"
        output_path = f"{template_def.id}{ext}"

        return RenderedScript(
            content=raw,
            command_lines=command_lines,
            platform=platform,
            output_path=output_path,
        )

    def validate_params_for_template(
        self,
        template_def: TemplateDef,
        params: Dict[str, str],
    ) -> Tuple[bool, Optional[str]]:
        """Pre-validate parameters before rendering.

        Checks:
        - All required parameters are present.
        - All parameter values pass the whitelist filter.

        Args:
            template_def: Template definition with param schema.
            params: User-provided parameter values.

        Returns:
            (True, None) if all parameters are valid.
            (False, error_message) if validation fails.

        Design:
            DC-0051
        """
        # Check required parameters
        for param in template_def.params:
            if param.required and param.name not in params:
                return (
                    False,
                    f"Missing required parameter: {param.name}",
                )

        # Whitelist check on all provided values
        for name, value in params.items():
            if not _WHITELIST_RE.match(value):
                return (
                    False,
                    f"Parameter '{name}' contains illegal characters",
                )

        return (True, None)
