"""Template registry for GIS Agent.

Provides in-memory indexing of TemplateDef objects for fast lookup by id.

Public API:
    TemplateRegistry — lookup, listing, and param schema access

Design: plan-core v1.0.0 (DC-0041)
"""

from pathlib import Path
from typing import List, Optional

from core.models import ParamDef, TemplateDef


class TemplateRegistry:
    """模板注册表。

    接收 ``templates.scanner.scan_templates()`` 的扫描结果构建，
    提供模板查询和参数 Schema 访问。

    Design:
        DC-0041
    """

    def __init__(self, templates: List[TemplateDef], template_dir: Path) -> None:
        """从扫描结果构建注册表。

        Args:
            templates: 扫描得到的 TemplateDef 列表（由 ``scan_templates`` 产出）。
            template_dir: 模板文件根目录，用于 ``get_template_path`` 解析绝对路径。
        """
        self._template_dir = template_dir
        self._registry: dict[str, TemplateDef] = {t.id: t for t in templates}

    def get_template(self, template_id: str) -> Optional[TemplateDef]:
        """按 ID 获取模板定义。

        Args:
            template_id: 模板唯一标识符。

        Returns:
            对应的 TemplateDef，若不存在则返回 None。
        """
        return self._registry.get(template_id)

    def list_templates(self) -> List[TemplateDef]:
        """获取所有模板列表。

        Returns:
            按 ID 字母顺序排序的 TemplateDef 列表。
        """
        return sorted(self._registry.values(), key=lambda t: t.id)

    def get_available_ids(self) -> List[str]:
        """获取所有模板 ID 列表（用于意图分类）。

        Returns:
            按字母顺序排序的 ID 列表。
        """
        return sorted(self._registry.keys())

    def get_param_schema(self, template_id: str) -> List[ParamDef]:
        """获取指定模板的参数定义列表。

        Args:
            template_id: 模板唯一标识符。

        Returns:
            参数定义列表。若模板不存在则返回空列表。
        """
        template = self._registry.get(template_id)
        if template is None:
            return []
        return list(template.params)

    def get_template_path(self, template_id: str) -> Path:
        """获取模板 .j2 文件的绝对路径。

        Args:
            template_id: 模板唯一标识符。

        Returns:
            模板文件的绝对路径。

        Raises:
            KeyError: 模板 ID 不存在于注册表中。
        """
        template = self._registry.get(template_id)
        if template is None:
            raise KeyError(f"Template not found: {template_id}")
        return (self._template_dir / template.template_file).resolve()
