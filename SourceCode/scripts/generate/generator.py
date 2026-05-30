"""LLM template generator.

Design: plan-j2-generate T-GEN-03, DC-0085
"""

import json
import logging
import re
from typing import Any

from llm.client import LLMClient
from llm.models import Message

from generate.models import ExtractedDoc, ParamDef, TemplateDefinition

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a GDAL command-line expert. Your task is to convert GDAL HTML documentation into a structured Jinja2 template definition for the GIS Agent system.

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

_FEW_SHOT_EXAMPLES = """
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
# Helpers
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


def _extract_template_vars(command_template: str) -> set[str]:
    """Extract all variable names used in a Jinja2 template."""
    template_vars = set(
        re.findall(r"\{\{\s*(\w+)(?:\s*\|[^}]*)?\s*\}\}", command_template)
    )
    if_vars = set(re.findall(r"{%\s*if\s+(\w+)\s*%}", command_template))
    return (template_vars | if_vars) - {"endif"}


def _parse_template_def(raw_json: str) -> TemplateDefinition:
    """Parse LLM JSON output into TemplateDefinition.

    Auto-completes missing params referenced in command_template
    to reduce bulk-generation failures.
    """
    cleaned = _strip_markdown_json(raw_json)
    data = json.loads(cleaned)

    params_raw = data.get("params") or []
    params = [_parse_param(p) for p in params_raw if p is not None]
    param_names = {p.name for p in params}

    # Auto-complete undeclared template variables as optional string params
    command_template = data["command_template"]
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
                    type="string",
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

    Design: DC-0085
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
            Message(role="user", content=_FEW_SHOT_EXAMPLES),
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
                system_prompt=_SYSTEM_PROMPT,
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
        except json.JSONDecodeError as exc:
            logger.debug("JSON parse failed: %s", exc)
            return None
        except (ValueError, KeyError) as exc:
            logger.debug("Template validation failed: %s", exc)
            return None
