"""Template scanner: discover and parse .j2 files from disk.

Scans a directory tree for ``*.j2`` files, reads the Jinja2 comment header
of each file, and produces ``TemplateDef`` / ``ParamDef`` objects.

Public API:
    scan_templates(template_dir) -> List[TemplateDef]
    parse_j2_header(j2_path) -> TemplateDef

Comment format (declarative header inside ``{# … #}`` blocks):

    {# @id template_id #}
    {# @name Human-readable name #}
    {# @description What this template does #}
    {# @param param_name param_type required|optional description #}
    {# @param param_name param_type required|optional description default=value #}

Example:

    {# @id shp2geojson #}
    {# @name Shapefile 转 GeoJSON #}
    {# @description 将 Shapefile 格式转换为 GeoJSON #}
    {# @param input file_path required 输入 Shapefile 路径 #}
    {# @param t_srs crs optional 目标坐标系 default=EPSG:4326 #}

Design: plan-templates v1.0.0 (DC-0050), plan-core v1.0.0 (DC-0041)
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
            tdef = parse_j2_header(j2_path)
        except ValueError as exc:
            logger.warning("Skipping %s: %s", j2_path, exc)
            continue
        results.append(tdef)
    return sorted(results, key=lambda t: t.id)


def parse_j2_header(j2_path: Path) -> TemplateDef:
    """Parse the comment header of a single ``.j2`` file.

    Reads only the first 50 lines to avoid loading large templates into
    memory.

    Args:
        j2_path: Path to the ``.j2`` file.

    Returns:
        ``TemplateDef`` built from the header comments.

    Raises:
        ValueError: If the header is missing ``@id``.
    """
    content = _read_header(j2_path)
    data: dict[str, str] = {}
    raw_params: List[str] = []

    for match in _HEADER_RE.finditer(content):
        key = match.group(1)
        value = match.group(2).strip()
        if key == "param":
            raw_params.append(value)
        else:
            data[key] = value

    template_id = data.get("id", "")
    if not template_id:
        raise ValueError(f"Missing @id in {j2_path}")

    # template_file is the relative path from template_dir root.
    # We don't know the root here, so we store the file name and let the
    # caller resolve relative to their root if needed.
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
