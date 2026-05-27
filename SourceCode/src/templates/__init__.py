"""Template engine module for GIS Agent.

Public API:
    TemplateEngine — Jinja2 template rendering engine
    Platform — target platform enum
    RenderedScript — rendered script dataclass
    quote_filter — shell-safe quoting filter
    safe_path_filter — workspace-relative path resolution filter
    ScriptSecurityChecker — post-render security validator
    scan_templates — discover .j2 files and parse headers
    parse_j2_header — parse a single .j2 file header

    TemplateError, TemplateNotFoundError, RenderError, SecurityCheckError

Design: plan-templates v1.0.0 (DC-0050 ~ DC-0054)
"""

from templates.engine import (
    Platform,
    RenderedScript,
    RenderError,
    ScriptSecurityChecker,
    SecurityCheckError,
    TemplateEngine,
    TemplateError,
    TemplateNotFoundError,
    quote_filter,
    safe_path_filter,
)
from templates.scanner import parse_j2_header, scan_templates

__all__ = [
    "Platform",
    "RenderedScript",
    "RenderError",
    "ScriptSecurityChecker",
    "SecurityCheckError",
    "TemplateEngine",
    "TemplateError",
    "TemplateNotFoundError",
    "quote_filter",
    "safe_path_filter",
    "parse_j2_header",
    "scan_templates",
]
