"""Parameter validator chain for GIS Agent.

Provides type-specific validation for template parameters.

Public API:
    ValidationResult — (is_valid, error_message) tuple alias
    ParamValidator — validates individual params and full template param sets

Design: plan-core v1.0.0 (DC-0042)
"""

import re
from typing import Callable, Dict, List, Optional, Tuple

from core.models import ParamDef, TemplateDef
from core.workspace import PathNotFoundError, Workspace

ValidationResult = Tuple[bool, Optional[str]]
# (is_valid, error_message)


class ParamValidator:
    """参数校验器链。

    每个参数类型对应一个校验器函数，按顺序执行：
    类型转换 → 格式校验 → 业务规则校验 → 路径存在性校验。

    Design:
        DC-0042
    """

    _EPSG_RE = re.compile(r"^EPSG:\d+$", re.IGNORECASE)
    """EPSG code pattern (e.g. EPSG:4326)."""

    def __init__(self, workspace: Workspace) -> None:
        """Args:
        workspace: 用于 file_path 类型的路径存在性校验（must_exist）。
            Workspace v2.0 是记忆锚点，不是安全边界；绝对路径直接放行。
        """
        self._workspace = workspace

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(self, param_def: ParamDef, value: str) -> ValidationResult:
        """对单个参数值执行完整校验链。

        Args:
            param_def: 参数定义（含类型、必填、约束）。
            value: 用户提供的值。

        Returns:
            (True, None) 表示校验通过。
            (False, error_msg) 表示校验失败，error_msg 可直接展示给用户。
        """
        if not value and param_def.required:
            return (False, f"参数 '{param_def.name}' 不能为空")

        if not value and not param_def.required:
            # Optional empty value is acceptable (will use default)
            return (True, None)

        validator = self._get_validator(param_def.type)
        return validator(param_def, value)

    def validate_all(
        self,
        template: TemplateDef,
        params: Dict[str, str],
    ) -> Tuple[Dict[str, str], List[str]]:
        """批量校验模板的所有参数。

        流程：
        1. 检查必填参数是否缺失。
        2. 逐个校验提供的参数值。
        3. 为缺失的可选参数填充默认值。
        4. 对 boolean 类型值进行规范化（转为 "true"/"false"）。

        Args:
            template: 模板定义（含参数 schema）。
            params: 用户提供的参数键值对。

        Returns:
            (valid_params, error_messages)
            valid_params: 校验通过的参数（含默认值填充、类型转换）。
            error_messages: 校验失败的错误信息列表。
        """
        valid_params: Dict[str, str] = {}
        error_messages: List[str] = []

        # Check required params
        for param_def in template.params:
            if param_def.required and param_def.name not in params:
                error_messages.append(
                    f"缺少必填参数: {param_def.name} ({param_def.description})"
                )

        # Validate provided params
        for param_def in template.params:
            if param_def.name in params:
                value = params[param_def.name]
                ok, error = self.validate(param_def, value)
                if ok:
                    # Normalize boolean values for template rendering
                    if param_def.type == "boolean":
                        valid_params[param_def.name] = self._normalize_boolean(value)
                    else:
                        valid_params[param_def.name] = value
                elif error is not None:
                    error_messages.append(error)
            elif not param_def.required and param_def.default is not None:
                # Fill in default for missing optional params
                valid_params[param_def.name] = param_def.default

        return valid_params, error_messages

    # ------------------------------------------------------------------
    # Type-specific validators
    # ------------------------------------------------------------------

    def _get_validator(self, param_type: str) -> Callable[[ParamDef, str], ValidationResult]:
        """Return the validator function for the given parameter type."""
        validators = {
            "file_path": self._validate_file_path,
            "crs": self._validate_crs,
            "string": self._validate_string,
            "boolean": self._validate_boolean,
            "integer": self._validate_integer,
        }
        return validators.get(param_type, self._validate_string)

    def _validate_file_path(self, param_def: ParamDef, value: str) -> ValidationResult:
        """Validate file path: non-empty, must_exist check via workspace."""
        if not value:
            return (False, f"参数 '{param_def.name}' 不能为空")

        if param_def.must_exist:
            try:
                self._workspace.resolve_path(value, must_exist=True)
            except PathNotFoundError as exc:
                return (False, f"参数 '{param_def.name}': 路径不存在 ({exc})")

        return (True, None)

    def _validate_crs(self, param_def: ParamDef, value: str) -> ValidationResult:
        """Validate CRS: must match EPSG:\\d+ pattern."""
        if self._EPSG_RE.match(value):
            return (True, None)
        return (
            False,
            f"参数 '{param_def.name}': CRS 格式无效，应为 EPSG:xxxx（如 EPSG:4326）",
        )

    def _validate_string(self, param_def: ParamDef, value: str) -> ValidationResult:
        """Validate string: non-empty."""
        if not value:
            return (False, f"参数 '{param_def.name}' 不能为空")
        return (True, None)

    def _validate_boolean(self, param_def: ParamDef, value: str) -> ValidationResult:
        """Validate boolean: must be one of yes/true/1/no/false/0."""
        lower = value.lower()
        if lower in ("yes", "true", "1", "no", "false", "0"):
            return (True, None)
        return (
            False,
            f"参数 '{param_def.name}': 布尔值格式无效，应为 yes/no/true/false/1/0",
        )

    def _validate_integer(self, param_def: ParamDef, value: str) -> ValidationResult:
        """Validate integer: must be parseable as int."""
        try:
            int(value)
            return (True, None)
        except ValueError:
            return (
                False,
                f"参数 '{param_def.name}': 整数格式无效",
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_boolean(value: str) -> str:
        """Convert various boolean representations to 'true' or 'false'."""
        return "true" if value.lower() in ("yes", "true", "1") else "false"
