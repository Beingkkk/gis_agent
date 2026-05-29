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
5. `command_template`: Jinja2 syntax using {{ param_name }} variables (flat names only, NEVER use dot notation like `{{ param.x }}`). Path/string params MUST use | quote filter. Use {% if param %}...{% endif %} for optional flags/params. CRITICAL: ONLY use params DECLARED in the `params` list. Do NOT reference any variable that is not declared.
6. `params`: Extract the most commonly used parameters (5-10 max, focus on the core workflow). For each:
   - `name`: parameter name (snake_case). For options with short+long forms like `-f`/`-of`, pick ONE name (prefer the long form without dash, e.g. "of" not "f")
   - `type`: one of "file_path", "crs", "string", "boolean", "integer", "float"
   - `required`: true/false
   - `description`: Chinese description
   - `default`: optional, only for non-required params
7. Type inference rules:
   - File/dataset paths -> file_path
   - Coordinate system definitions (EPSG, WKT, PROJ strings) -> crs
   - On/off flags without values -> boolean
   - Numeric values -> integer/float
   - Everything else -> string
8. `concepts`: 1-2 core concept explanations in Chinese
9. `notes`: 1-2 usage notes in Chinese
10. `common_errors`: Extract 1-2 common errors from the documentation, each with `error_text` and `explanation` in Chinese
11. `seealso`: Related GIS Agent template IDs. ONLY include if you are certain the template exists. When in doubt, leave empty.

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
  "command_template": "ogr2ogr{% if of %} -f {{ of | quote }}{% endif %}{% if t_srs %} -t_srs {{ t_srs | quote }}{% endif %}{% if s_srs %} -s_srs {{ s_srs | quote }}{% endif %}{% if where %} -where {{ where | quote }}{% endif %}{% if sql %} -sql {{ sql | quote }}{% endif %}{% if select %} -select {{ select | quote }}{% endif %}{% if nln %} -nln {{ nln | quote }}{% endif %}{% if append %} -append{% endif %} {{ output | safe_path | quote }} {{ input | safe_path | quote }}",
  "params": [
    {"name": "input", "type": "file_path", "required": true, "description": "输入矢量文件路径或数据源（源数据集）"},
    {"name": "output", "type": "file_path", "required": true, "description": "输出矢量文件路径或数据源（目标数据集）"},
    {"name": "of", "type": "string", "required": false, "description": "输出格式名称，如 GeoJSON、ESRI Shapefile、GML 等"},
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

    params = [_parse_param(p) for p in data.get("params", [])]
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

        try:
            raw_response = self._client.chat(
                system_prompt=_SYSTEM_PROMPT,
                messages=messages,
                temperature=0.1,
            )
        except Exception as exc:
            logger.warning("LLM generation failed: %s", exc)
            return None, f"LLM call failed: {exc}"

        try:
            template_def = _parse_template_def(raw_response)
        except json.JSONDecodeError as exc:
            logger.warning("JSON parse failed: %s", exc)
            return None, f"JSON parse failed: {exc}"
        except (ValueError, KeyError) as exc:
            logger.warning("Template validation failed: %s", exc)
            return None, f"Template validation failed: {exc}"

        return template_def, ""
