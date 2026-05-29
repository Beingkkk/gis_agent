"""Template scanner: discover and parse .j2 files from disk.

Scans a directory tree for ``*.j2`` files, reads the Jinja2 comment header
of each file, and produces ``TemplateDef`` / ``ParamDef`` objects.

Comment format (declarative header inside ``{# … #}`` blocks):

    {# @id template_id #}
    {# @name Human-readable name #}
    {# @description What this template does #}
    {# @concept "Term" — Explanation of the concept #}
    {# @note A usage hint or precondition #}
    {# @seealso related_template_id #}
    {# @common_error "Error text" — Cause and fix suggestion #}
    {# @param param_name param_type required|optional description #}
    {# @param param_name param_type required|optional description default=value #}

Example:

    {# @id shp2geojson #}
    {# @name Shapefile 转 GeoJSON #}
    {# @description 将 Shapefile 格式转换为 GeoJSON #}
    {# @concept "GeoJSON" — 一种基于 JSON 的地理数据交换格式 #}
    {# @note 输出路径自动加时间戳防覆盖 #}
    {# @seealso vector/merge_shp #}
    {# @param input file_path required 输入 Shapefile 路径 #}
    {# @param t_srs crs optional 目标坐标系 default=EPSG:4326 #}

Design: plan-templates v1.1.0 (DC-0050, DC-0055), plan-core v1.0.0 (DC-0041)
"""

import logging
import re
from pathlib import Path
from typing import List, Optional

from core.models import ParamDef, TemplateDef

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regexes
# ---------------------------------------------------------------------------

_HEADER_RE = re.compile(r"\{\#\s*@(\w+)\s+(.*?)\s*\#\}")
"""Match ``{# @key value #}`` and capture ``key`` and ``value``."""

# Extended knowledge metadata tags (DC-0055 / ADR-0001)
_CONCEPT_RE = re.compile(r'^"([^"]+)"\s*—\s*(.+)$')
"""Match ``{@concept "Term" — Explanation #}``."""

_COMMON_ERROR_RE = re.compile(r'^"([^"]+)"\s*—\s*(.+)$')
"""Match ``{@common_error "Error" — Fix #}``."""

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_templates(template_dir: Path) -> List[TemplateDef]:
    """Recursively scan *template_dir* for ``*.j2`` files and parse headers.

    Files that lack a valid ``@id`` are skipped with a logged warning.

    Args:
        template_dir: Root directory containing ``*.j2`` template files.

    Returns:
        List of ``TemplateDef`` in alphabetical order by *id*.
    """
    results: List[TemplateDef] = []
    for j2_path in sorted(template_dir.rglob("*.j2")):
        try:
            tdef = parse_j2_header(j2_path, template_dir)
        except ValueError as exc:
            logger.warning("Skipping %s: %s", j2_path, exc)
            continue
        results.append(tdef)
    return sorted(results, key=lambda t: t.id)


def parse_j2_header(
    j2_path: Path,
    template_dir: Path | None = None,
) -> TemplateDef:
    """Parse the comment header of a single ``.j2`` file.

    Reads only the first 50 lines to avoid loading large templates into
    memory.

    Args:
        j2_path: Path to the ``.j2`` file.
        template_dir: Root directory of the template tree. When provided,
            ``template_file`` is stored as a path relative to this root
            (e.g. ``"vector/shp2geojson.j2"``). When omitted, only the
            file name is stored.

    Returns:
        ``TemplateDef`` built from the header comments.

    Raises:
        ValueError: If the header is missing ``@id``.
    """
    content = _read_header(j2_path)
    data: dict[str, str] = {}
    raw_params: List[str] = []
    concepts: List[tuple[str, str]] = []
    notes: List[str] = []
    seealso: List[str] = []
    common_errors: List[tuple[str, str]] = []

    for match in _HEADER_RE.finditer(content):
        key = match.group(1)
        value = match.group(2).strip()
        if key == "param":
            raw_params.append(value)
        elif key == "concept":
            parsed = _parse_concept(value)
            if parsed:
                concepts.append(parsed)
        elif key == "note":
            notes.append(value)
        elif key == "seealso":
            seealso.append(value)
        elif key == "common_error":
            parsed = _parse_common_error(value)
            if parsed:
                common_errors.append(parsed)
        else:
            data[key] = value

    template_id = data.get("id", "")
    if not template_id:
        raise ValueError(f"Missing @id in {j2_path}")

    # Store relative path when template_dir is known (scanning), otherwise
    # fall back to the file name for backwards compatibility.
    if template_dir is not None:
        template_file = str(j2_path.relative_to(template_dir).as_posix())
    else:
        template_file = str(j2_path.name)

    name = data.get("name", template_id)
    description = data.get("description", "")

    params = [_parse_param_line(line) for line in raw_params]

    return TemplateDef(
        id=template_id,
        name=name,
        description=description,
        template_file=template_file,
        params=params,
        concepts=concepts,
        notes=notes,
        seealso=seealso,
        common_errors=common_errors,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_header(j2_path: Path, max_lines: int = 50) -> str:
    """Read the first *max_lines* of *j2_path*."""
    lines: List[str] = []
    try:
        with open(j2_path, encoding="utf-8") as fh:
            for _ in range(max_lines):
                line = fh.readline()
                if not line:
                    break
                lines.append(line)
    except OSError as exc:
        logger.warning("Cannot read %s: %s", j2_path, exc)
    return "".join(lines)


def _parse_param_line(line: str) -> ParamDef:
    """Parse a single ``@param`` value into ``ParamDef``.

    Format::

        name type required|optional description [default=value]

    The ``default=`` clause is optional.  It is extracted from the tail of
    the description by searching for the last occurrence of `` default=``.

    Args:
        line: Raw ``@param`` value (everything after the keyword).

    Returns:
        ``ParamDef`` populated from the line.

    Raises:
        ValueError: If the line does not contain at least name, type,
            and required/optional marker.
    """
    tokens = line.split(None, 3)
    if len(tokens) < 3:
        raise ValueError(f"Invalid @param line: {line!r}")

    name = tokens[0]
    ptype = tokens[1]
    required_str = tokens[2]
    required = required_str == "required"

    description = tokens[3] if len(tokens) > 3 else ""
    default: Optional[str] = None

    if " default=" in description:
        desc_part, _, default_part = description.rpartition(" default=")
        description = desc_part
        default = default_part

    return ParamDef(
        name=name,
        type=ptype,
        required=required,
        description=description,
        default=default,
    )


def _parse_concept(value: str) -> tuple[str, str] | None:
    """Parse ``@concept`` value into (term, explanation).

    Expected format: ``"Term" — Explanation``

    Returns:
        (term, explanation) tuple, or None if parsing fails.
    """
    match = _CONCEPT_RE.match(value)
    if match:
        return (match.group(1).strip(), match.group(2).strip())
    logger.debug("Failed to parse @concept: %r", value)
    return None


def _parse_common_error(value: str) -> tuple[str, str] | None:
    """Parse ``@common_error`` value into (error_text, fix).

    Expected format: ``"Error text" — Cause and fix``

    Returns:
        (error_text, fix) tuple, or None if parsing fails.
    """
    match = _COMMON_ERROR_RE.match(value)
    if match:
        return (match.group(1).strip(), match.group(2).strip())
    logger.debug("Failed to parse @common_error: %r", value)
    return None
