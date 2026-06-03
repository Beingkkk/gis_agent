"""Shared template generation engine.

Extracted from scripts/generate/generator.py to unify online mode and CLI batch mode.

Design:
    DC-0094
"""

import ast
import json
import json5
import logging
import re
from typing import Any, Callable

from llm.client import LLMClient
from llm.models import Message

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a GDAL command-line expert. Your task is to convert GDAL HTML documentation into a structured Jinja2 template definition for the GIS Agent system.

Rules:
1. `id`: lowercase + underscores only, globally unique, descriptive
2. `name`: Chinese name, 2-30 characters, describes the main use case
3. `description`: One-sentence Chinese description of the tool's primary function
4. `category`: one of "vector", "raster", "general"
5. `keywords`: 3-5 search keywords in Chinese or English. Include: format abbreviations (e.g. "shp"), common format names (e.g. "geojson"), operation verbs (e.g. "转换"). These are used for template matching ONLY, not shown to users.
6. `command_template`: Jinja2 syntax using {{ param_name }} variables (flat names only, NEVER use dot notation like `{{ param.x }}`). Path/string params MUST use | quote filter. Use {% if param %}...{% endif %} for optional flags/params. CRITICAL: ONLY use params DECLARED in the `params` list. Do NOT reference any variable that is not declared.
7. `params`: Extract the most commonly used parameters (5-10 max, focus on the core workflow). For each:
   - `name`: parameter name (snake_case). For options with short+long forms like `-f`/`-of`, pick ONE name (prefer the long form without dash, e.g. "of" not "f")
   - `type`: one of "file_path", "folder_path", "crs", "string", "text", "boolean", "integer", "float", "enum", "format"
   - `required`: true/false
   - `description`: Chinese description
   - `default`: optional, only for non-required params
   - `options`: REQUIRED for "enum" and "format" types. A list of string values. For "format", list the most common GDAL format names (e.g. ["GeoJSON", "ESRI Shapefile", "GPKG", "KML"]). For "enum", list the valid choices from the documentation.
8. Type inference rules:
   - File/dataset paths -> file_path
   - Directory paths -> folder_path
   - Coordinate system definitions (EPSG, WKT, PROJ strings) -> crs
   - On/off flags without values -> boolean
   - Numeric values -> integer/float
   - Output format names (GeoJSON, Shapefile, etc.) -> format (with options)
   - Multi-line configuration values (KEY=VALUE pairs) -> text
   - Everything else -> string
9. `concepts`: 1-2 core concept explanations in Chinese
10. `notes`: 1-2 usage notes in Chinese
11. `common_errors`: Extract 1-2 common errors from the documentation, each with `error_text` and `explanation` in Chinese
12. `seealso`: Related GIS Agent template IDs. ONLY include if you are certain the template exists. When in doubt, leave empty.

Output MUST be valid JSON only. No markdown code blocks. No extra text."""

FEW_SHOT_EXAMPLES = """
Example: ogr2ogr format conversion
---
GDAL Tool: ogr2ogr

SYNOPSIS:
Usage: ogr2ogr [--help] [--long-usage] [--help-general] [-of <output_format>] [-lco <NAME>=<VALUE>]... [[-append]|[-overwrite]] [-update] [-sql <statement>|@<filename>] [-where <restricted_where>|@<filename>] [-select <field_list>] [-nln <name>] [-nlt <type>]... [-s_srs <srs_def>] [-t_srs <srs_def>] <dst_dataset_name> <src_dataset_name> [<layer_name>]...

DESCRIPTION:
Converts simple features data between file formats. It can also perform various operations during the process, such as spatial or attribute selection, reducing the set of attributes, setting the output coordinate system or even reprojecting the features during translation.

Output:
{
  "id": "ogr2ogr_convert",
  "name": "矢量格式转换",
  "description": "使用 ogr2ogr 将矢量数据在不同格式之间转换，支持坐标系转换",
  "category": "vector",
  "keywords": ["shp", "shapefile", "geojson", "gpkg", "kml", "格式转换", "矢量转换"],
  "command_template": "ogr2ogr{% if of %} -f {{ of | quote }}{% endif %}{% if t_srs %} -t_srs {{ t_srs | quote }}{% endif %}{% if s_srs %} -s_srs {{ s_srs | quote }}{% endif %}{% if where %} -where {{ where | quote }}{% endif %}{% if sql %} -sql {{ sql | quote }}{% endif %}{% if select %} -select {{ select | quote }}{% endif %}{% if nln %} -nln {{ nln | quote }}{% endif %}{% if append %} -append{% endif %} {{ output | safe_path | quote }} {{ input | safe_path | quote }}",
  "params": [
    {"name": "input", "type": "file_path", "required": true, "description": "输入矢量文件路径或数据源（源数据集）"},
    {"name": "output", "type": "file_path", "required": true, "description": "输出矢量文件路径或数据源（目标数据集）"},
    {"name": "of", "type": "format", "required": false, "description": "输出格式名称", "default": "GeoJSON", "options": ["GeoJSON", "ESRI Shapefile", "GPKG", "KML", "MapInfo File"]},
    {"name": "t_srs", "type": "crs", "required": false, "description": "目标空间参考系统定义，用于坐标转换（如 EPSG:4326）"},
    {"name": "s_srs", "type": "crs", "required": false, "description": "源数据的空间参考系统定义（如 EPSG:4326）"},
    {"name": "where", "type": "string", "required": false, "description": "属性查询条件（SQL WHERE 子句）"},
    {"name": "sql", "type": "string", "required": false, "description": "SQL 查询语句"},
    {"name": "select", "type": "string", "required": false, "description": "要复制的字段列表（逗号分隔）"},
    {"name": "nln", "type": "string", "required": false, "description": "输出图层新名称"},
    {"name": "append", "type": "boolean", "required": false, "description": "追加到现有图层而不是创建新图层"}
  ],
  "concepts": [
    "ogr2ogr 是 GDAL 的矢量格式转换工具，支持 Shapefile、GeoJSON、GML、KML、PostGIS 等数十种格式互转",
    "转换过程中可同时执行坐标系变换、属性筛选、空间裁剪等多种空间数据处理操作"
  ],
  "notes": [
    "目标格式默认从文件扩展名自动判断，也可用 -f 显式指定",
    "追加模式(-append)要求目标数据源已存在对应图层"
  ],
  "common_errors": [
    {"error_text": "Unable to open datasource", "explanation": "输入文件路径不存在，或指定的格式不受支持"},
    {"error_text": "Layer does not exist", "explanation": "指定的源图层名称错误，或目标格式不支持该图层类型"}
  ],
  "seealso": []
}

The example above shows ONLY the output format. You MUST generate a template for the ACTUAL tool described in the input below."""

# ---------------------------------------------------------------------------
# JSON parsing utilities
# ---------------------------------------------------------------------------


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


# Valid JSON escape sequences per RFC 8259.
_VALID_JSON_ESCAPES: set[str] = {'"', '\\', '/', 'b', 'f', 'n', 'r', 't', 'u'}


def _fix_json_keys(text: str) -> str:
    """Fix unquoted JSON object keys in LLM output.

    LLMs sometimes output {name: "value"} instead of {"name": "value"}.
    This fixes the most common cases while preserving already-quoted keys.
    """
    # Fix 1: keys immediately after { or , (most common pattern)
    fixed = re.sub(r'(?<=[{,])\s*([a-zA-Z_]\w*)\s*:', r'"\1":', text)
    # Fix 2: keys at start of line (indented object members)
    fixed = re.sub(r'(^|\n)\s*([a-zA-Z_]\w*)\s*:', r'\1"\2":', fixed)
    return fixed


def _fix_json_invalid_escapes(text: str) -> str:
    r"""Fix invalid escape sequences inside JSON string values.

    LLMs frequently output Windows paths (``C:\Users\...``) or other
    text containing backslashes that are not valid JSON escapes.
    In JSON only ``\\``, ``\\\"``, ``\/``, ``\\b``, ``\\f``, ``\\n``,
    ``\\r``, ``\\t`` and ``\\uXXXX`` are valid inside strings.

    Args:
        text: JSON-like text that may contain invalid escapes.

    Returns:
        Text with invalid escapes converted to doubled backslashes.
    """
    result: list[str] = []
    in_string = False
    escaped = False

    i = 0
    while i < len(text):
        char = text[i]
        if not in_string:
            if char == '"':
                in_string = True
            result.append(char)
            i += 1
        else:
            if escaped:
                if char == 'u':
                    # \uXXXX — verify 4 hex digits follow
                    hex_part = text[i + 1 : i + 5]
                    if (
                        len(hex_part) == 4
                        and all(c in "0123456789abcdefABCDEF" for c in hex_part)
                    ):
                        result.append(char)
                    else:
                        # Invalid \u — double the preceding backslash
                        result.append("\\")
                        result.append(char)
                elif char not in _VALID_JSON_ESCAPES:
                    # Invalid escape (e.g. \U, \x, \d) — double the backslash
                    result.append("\\")
                    result.append(char)
                else:
                    result.append(char)
                escaped = False
                i += 1
            elif char == '\\':
                result.append(char)
                escaped = True
                i += 1
            elif char == '"':
                in_string = False
                result.append(char)
                i += 1
            else:
                result.append(char)
                i += 1

    return "".join(result)


def _fix_unescaped_quotes_by_error(text: str, exc: json.JSONDecodeError) -> str | None:
    """Try to fix unescaped quotes using the JSON parse error position.

    When ``json.loads`` fails with *Expecting ',' delimiter* or similar,
    it often means a string was prematurely closed by an unescaped quote
    inside the string value.  We look backwards from the error position
    for the nearest unescaped ``\"`` and try adding a backslash before it.

    Args:
        text: The text that failed to parse.
        exc: The ``json.JSONDecodeError`` raised by ``json.loads``.

    Returns:
        Fixed text if a repair was found, otherwise ``None``.
    """
    error_pos = exc.pos if hasattr(exc, "pos") else None
    if error_pos is None or error_pos <= 0:
        return None

    # Walk backwards from the error position looking for an unescaped quote.
    # If fixing one quote still fails, recurse to fix additional quotes.
    for i in range(error_pos - 1, -1, -1):
        if text[i] == '"' and (i == 0 or text[i - 1] != "\\"):
            candidate = text[:i] + "\\" + text[i:]
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError as exc2:
                # There may be multiple unescaped quotes — try fixing the next one
                sub_fixed = _fix_unescaped_quotes_by_error(candidate, exc2)
                if sub_fixed is not None:
                    return sub_fixed
                continue

    return None


def _fix_json_string_issues(text: str) -> str:
    """Fix unescaped control characters inside JSON string values.

    LLMs frequently output raw newlines or unescaped quotes inside
    string values (e.g. in ``command_template`` or ``description``).
    This walks the text character-by-character to accurately track
    whether we are inside a string and escapes offending characters.

    Args:
        text: JSON-like text that may contain unescaped characters.

    Returns:
        Text with unescaped newlines and carriage returns inside strings
        converted to ``\\n`` / ``\\r``.
    """
    result: list[str] = []
    in_string = False
    escaped = False

    for char in text:
        if not in_string:
            if char == '"':
                in_string = True
            result.append(char)
        else:
            if escaped:
                result.append(char)
                escaped = False
            elif char == '\\':
                result.append(char)
                escaped = True
            elif char == '"':
                in_string = False
                result.append(char)
            elif char == '\n':
                result.append('\\n')
            elif char == '\r':
                result.append('\\r')
            else:
                result.append(char)

    return "".join(result)


def _clean_json(text: str) -> str:
    """Apply all safe JSON fix heuristics in a consistent order.

    The order matters: fix string internals (newlines, escapes) before
    structural fixes (keys, trailing commas) so structural patterns are
    matched against clean string boundaries.
    """
    text = _fix_json_string_issues(text)     # unescaped newlines / \r
    text = _fix_json_invalid_escapes(text)   # C:\Users style backslashes
    text = _fix_json_keys(text)              # bare keys (for json path)
    return text


def parse_generated_response(text: str) -> dict[str, Any]:
    """Parse LLM response text into a dict using multiple fallback strategies.

    Tries a progressively more forgiving sequence:

    1. **json5** — handles bare keys, single-quoted strings, trailing commas.
    2. Light-weight cleanup (markdown strip + newline/escape fix) + **json5**.
    3. Extract ``{...}`` block + **json5**.
    4. Full cleanup (add bare-key fix) + **json.loads** + back-tracking
       quote repair for unescaped double quotes inside strings.
    5. ``ast.literal_eval`` as the final fallback.

    Design: DC-0094, ADR-0002

    Args:
        text: Raw LLM response text.

    Returns:
        Parsed dict.

    Raises:
        ValueError: If JSON parsing fails after all strategies.
    """
    cleaned = _strip_markdown_json(text)

    # --- Strategy 1: json5 (bare keys, single quotes, trailing commas) ---
    try:
        return json5.loads(cleaned)  # type: ignore[no-any-return]
    except ValueError:
        pass

    # --- Strategy 2: fix newlines/escapes + json5 ---
    fixed = _fix_json_string_issues(_fix_json_invalid_escapes(cleaned))
    if fixed != cleaned:
        try:
            return json5.loads(fixed)  # type: ignore[no-any-return]
        except ValueError:
            pass

    # --- Strategy 3: extract {...} block + json5 ---
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        extracted = cleaned[first_brace : last_brace + 1]
        try:
            return json5.loads(extracted)  # type: ignore[no-any-return]
        except ValueError:
            pass
        extracted_fixed = _fix_json_string_issues(_fix_json_invalid_escapes(extracted))
        if extracted_fixed != extracted:
            try:
                return json5.loads(extracted_fixed)  # type: ignore[no-any-return]
            except ValueError:
                pass

    # --- Strategy 4: json with full repairs (for unescaped quotes) ---
    # json5 doesn't expose precise error positions, so we fall back to
    # json.loads for the back-tracking quote repair which needs char positions.
    json_ready = _fix_json_keys(_fix_json_string_issues(_fix_json_invalid_escapes(cleaned)))
    last_error: Exception | None = None
    try:
        return json.loads(json_ready)  # type: ignore[no-any-return]
    except json.JSONDecodeError as exc:
        last_error = exc
        fixed_quotes = _fix_unescaped_quotes_by_error(json_ready, exc)
        if fixed_quotes is not None:
            try:
                return json.loads(fixed_quotes)  # type: ignore[no-any-return]
            except json.JSONDecodeError as exc2:
                last_error = exc2

    # --- Strategy 5: ast.literal_eval (Python dict literal) ---
    try:
        ast_result = ast.literal_eval(_fix_json_keys(cleaned))
        if isinstance(ast_result, dict):
            logger.info("Parsed LLM output using ast.literal_eval fallback")
            return ast_result  # type: ignore[no-any-return]
    except (ValueError, SyntaxError) as exc:
        logger.debug("AST parse fallback failed: %s", exc)

    # Log raw text on failure to aid debugging
    preview = text[:800] if len(text) > 800 else text
    logger.warning(
        "JSON parse failed after all strategies. Raw text preview:\n%s",
        preview,
    )

    raise ValueError(f"JSON parse failed: {last_error}")


# ---------------------------------------------------------------------------
# Parameter utilities
# ---------------------------------------------------------------------------


def sanitize_params(params: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fix common param issues from LLM generation.

    Args:
        params: Raw param dicts from LLM output.

    Returns:
        Sanitized param dicts.
    """
    result: list[dict[str, Any]] = []
    for p in params:
        if p is None:
            continue
        param = dict(p)

        # Fix 1: required=True with default -> make non-required
        if param.get("required") is True and param.get("default") is not None:
            logger.info(
                "Fixing param '%s': required=true but has default, "
                "setting required=false",
                param.get("name", "?"),
            )
            param["required"] = False

        # Fix 2: enum/format without options -> add placeholder
        if param.get("type") in ("enum", "format") and not param.get("options"):
            logger.info(
                "Fixing param '%s': %s type has empty options, adding placeholder",
                param.get("name", "?"),
                param["type"],
            )
            param["options"] = ["(see documentation)"]

        result.append(param)
    return result


def _extract_template_vars(command_template: str) -> set[str]:
    """Extract all variable names used in a Jinja2 template."""
    template_vars = set(
        re.findall(r"\{\{\s*(\w+)(?:\s*\|[^}]*)?\s*\}\}", command_template)
    )
    if_vars = set(re.findall(r"{%\s*if\s+(\w+)\s*%}", command_template))
    return (template_vars | if_vars) - {"endif"}


def auto_complete_params(body: str, params: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Auto-complete undeclared template variables as optional boolean params.

    Args:
        body: Jinja2 template body.
        params: Existing param dicts.

    Returns:
        Params with auto-completed entries appended.
    """
    param_names = {p.get("name", "") for p in params}
    undeclared = _extract_template_vars(body) - param_names
    if not undeclared:
        return list(params)

    logger.info(
        "Auto-completing %d undeclared params: %s",
        len(undeclared),
        sorted(undeclared),
    )
    result = list(params)
    for name in sorted(undeclared):
        result.append(
            {
                "name": name,
                "type": "boolean",
                "required": False,
                "description": "(auto-completed)",
            }
        )
    return result


def assemble_j2_body(data: dict[str, Any]) -> str:
    """Assemble LLM-generated structured data into a complete .j2 template file.

    Replicates the CLI renderer (scripts/generate/renderer.py) so that the
    API and WebSocket endpoints produce the same full .j2 format as the
    batch generation tool.

    Args:
        data: Parsed LLM response dict containing id/template_id, name,
            description, category, keywords, command_template/body, params,
            concepts, notes, common_errors, seealso.

    Returns:
        Complete .j2 file content as a single string.

    Design:
        DC-0094
    """
    lines: list[str] = []

    tid = data.get("template_id") or data.get("id", "generated")
    name = data.get("name", "Generated Template")
    description = data.get("description", "")
    category = data.get("category", "general")

    # Header comments — use % formatting to avoid f-string issues with {#
    lines.append("{# @id %s #}" % tid)
    lines.append("{# @name %s #}" % name)
    lines.append("{# @description %s #}" % description)
    lines.append("{# @category %s #}" % category)

    for keyword in data.get("keywords", []):
        lines.append("{# @keyword %s #}" % keyword)

    for concept in data.get("concepts", []):
        lines.append('{# @concept "%s" #}' % concept)

    for note in data.get("notes", []):
        lines.append("{# @note %s #}" % note)

    for ref in data.get("seealso", []):
        lines.append("{# @seealso %s #}" % ref)

    for err in data.get("common_errors", []):
        if isinstance(err, dict):
            err_text = err.get("error_text", "")
            explanation = err.get("explanation", "")
        else:
            err_text = str(err)
            explanation = ""
        lines.append('{# @common_error "%s" — %s #}' % (err_text, explanation))

    params = data.get("params", [])
    for param in params:
        if param is None:
            continue
        req = "required" if param.get("required", True) else "optional"
        default = ""
        if param.get("default") is not None:
            default = " default=%s" % param["default"]
        options = ""
        if param.get("options"):
            options = " options=%s" % ",".join(str(o) for o in param["options"])
        lines.append(
            "{# @param %s %s %s %s%s%s #}"
            % (
                param.get("name", ""),
                param.get("type", "string"),
                req,
                param.get("description", ""),
                default,
                options,
            )
        )

    lines.append("")

    # Command body
    body = data.get("body") or data.get("command_template", "")
    lines.append("@echo off")
    lines.append("REM Generated by GIS Agent")
    lines.append("REM Template: %s" % tid)
    lines.append("")
    lines.append(body)
    lines.append("")
    lines.append("REM Done")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Message building
# ---------------------------------------------------------------------------


def build_generation_messages(document_text: str) -> list[Message]:
    """Build the few-shot message list for template generation.

    Args:
        document_text: Cleaned GDAL documentation text.

    Returns:
        Message list: user(few-shot) → assistant(understood) → user(document).
    """
    return [
        Message(role="user", content=FEW_SHOT_EXAMPLES),
        Message(
            role="assistant",
            content="Understood. I will analyze the provided GDAL "
            "documentation and generate a Jinja2 template definition "
            "in valid JSON format.",
        ),
        Message(role="user", content=document_text),
    ]


# ---------------------------------------------------------------------------
# Generation entry points
# ---------------------------------------------------------------------------


def generate_template_sync(
    client: LLMClient,
    document_text: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Generate a template definition synchronously with retry logic.

    Attempt 1: temperature=0.1
    Attempt 2: temperature=0.2 with "pure JSON" hint (if parse fails)

    Args:
        client: LLMClient instance.
        document_text: Cleaned GDAL documentation text.
        config: Generation config (category, tool_source, etc.).

    Returns:
        Parsed template definition dict.

    Raises:
        ValueError: If JSON parsing fails after retry.
        Exception: If LLM call fails (propagated from client.chat).
    """
    messages = build_generation_messages(document_text)

    # Attempt 1
    logger.info("Generating template (attempt 1, temp=0.1)")
    response_text = client.chat(
        system_prompt=SYSTEM_PROMPT,
        messages=messages,
        temperature=0.1,
    )

    try:
        return parse_generated_response(response_text)
    except ValueError as exc:
        logger.info("Generation parse failed (attempt 1): %s", exc)

    # Attempt 2: retry with adjusted prompt
    logger.info("Retrying generation (attempt 2, temp=0.2)")
    retry_messages = messages + [
        Message(role="assistant", content=response_text),
        Message(
            role="user",
            content="Your previous response could not be parsed as valid JSON. "
            "Please output ONLY valid JSON, no markdown code blocks, no extra text.",
        ),
    ]
    response_text2 = client.chat(
        system_prompt=SYSTEM_PROMPT,
        messages=retry_messages,
        temperature=0.2,
    )

    try:
        return parse_generated_response(response_text2)
    except ValueError as exc2:
        logger.error("Generation parse failed after retry: %s", exc2)
        raise ValueError(f"JSON parse failed after retry: {exc2}") from exc2


def generate_template_stream(
    client: LLMClient,
    document_text: str,
    config: dict[str, Any],
    on_chunk: Callable[[str], None],
) -> str:
    """Generate a template definition with streaming output.

    Uses LLMClient.chat_stream() to yield text chunks in real-time.
    The caller's on_chunk callback receives each chunk as it is generated.

    If the streamed output cannot be parsed as valid JSON, a silent retry
    is performed using a non-streaming call with a "pure JSON" hint.
    The retry output is NOT streamed to the caller — only the final text
    is returned — so the caller should re-parse the returned text.

    Args:
        client: LLMClient instance.
        document_text: Cleaned GDAL documentation text.
        config: Generation config (category, tool_source, etc.).
        on_chunk: Callback invoked for each text chunk.

    Returns:
        Full concatenated response text.  If the first stream failed to
        parse, this is the text from the retry attempt.

    Raises:
        ValueError: If JSON parsing fails after the retry attempt.
        Exception: If LLM call fails (propagated from client.chat_stream
            or client.chat).
    """
    messages = build_generation_messages(document_text)

    # Attempt 1: stream
    logger.info("Streaming template generation (attempt 1, temp=0.1)")
    chunks: list[str] = []
    for chunk in client.chat_stream(
        system_prompt=SYSTEM_PROMPT,
        messages=messages,
        temperature=0.1,
    ):
        chunks.append(chunk)
        on_chunk(chunk)

    full_text = "".join(chunks)

    # Empty response — nothing to parse, return as-is
    if not full_text.strip():
        return full_text

    # Verify the streamed output is parseable
    try:
        parse_generated_response(full_text)
        return full_text
    except ValueError as exc:
        logger.info("Stream parse failed (attempt 1): %s", exc)

    # Attempt 2: retry silently (non-streaming) with adjusted prompt
    logger.info("Retrying generation (attempt 2, temp=0.2)")
    retry_messages = messages + [
        Message(role="assistant", content=full_text),
        Message(
            role="user",
            content="Your previous response could not be parsed as valid JSON. "
            "Please output ONLY valid JSON, no markdown code blocks, no extra text.",
        ),
    ]
    retry_text = client.chat(
        system_prompt=SYSTEM_PROMPT,
        messages=retry_messages,
        temperature=0.2,
    )

    # Verify retry output is parseable before returning
    try:
        parse_generated_response(retry_text)
    except ValueError as exc2:
        logger.error("Generation parse failed after retry: %s", exc2)
        raise ValueError(f"JSON parse failed after retry: {exc2}") from exc2

    return retry_text
