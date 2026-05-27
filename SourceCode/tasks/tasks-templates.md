# tasks-templates — 模板引擎模块实现任务清单

| 项目 | 内容 |
|------|------|
| 来源 Plan | [plan-templates](../Document/plan-templates.md) v1.0.0 |
| 状态 | 待实现 |
| 创建日期 | 2026-05-27 |

---

## 前置说明

本模块依赖 plan-core 中定义的 `TemplateDef` 和 `ParamDef` 数据模型。由于 core 模块的 TemplateRegistry 尚未实现，需先创建基础模型文件供 templates 模块使用。

---

## Phase 1: 基础模型与模块骨架

| 任务 ID | 任务名称 | 关联设计决策 | 优先级 | 状态 |
|:-------:|---------|:----------:|:------:|:----:|
| T-01 | 创建 `src/core/models.py`（`ParamDef` + `TemplateDef`） | DC-0041 | P0 | 待办 |
| T-02 | 创建 `data/templates/` 模块目录与 `__init__.py` | — | P0 | 待办 |
| T-03 | 编写 templates 单元测试骨架（TDD） | DC-0050~0054 | P0 | 待办 |

---

## Phase 2: 模板引擎核心实现（TDD 驱动）

| 任务 ID | 任务名称 | 关联设计决策 | 优先级 | 状态 |
|:-------:|---------|:----------:|:------:|:----:|
| T-04 | 实现 `Platform` Enum + `RenderedScript` dataclass | DC-0054 | P0 | 待办 |
| T-05 | 实现异常类型（`TemplateError` 族） | — | P0 | 待办 |
| T-06 | 实现 `quote_filter`（`shlex.quote` 封装） | DC-0051, DC-0053 | P0 | 待办 |
| T-07 | 实现 `safe_path_filter`（调用 `Workspace.resolve_path`） | DC-0053, DC-0051 | P0 | 待办 |
| T-08 | 实现 `ScriptSecurityChecker`（正则模式匹配） | DC-0052 | P0 | 待办 |
| T-09 | 实现 `TemplateEngine` 类（`render()` + `validate_params_for_template()`） | DC-0050~0054 | P0 | 待办 |

---

## Phase 3: 模板文件与注册表

| 任务 ID | 任务名称 | 关联设计决策 | 优先级 | 状态 |
|:-------:|---------|:----------:|:------:|:----:|
| T-10 | 创建 `registry.json` 模板注册表 | DC-0041, DC-0050 | P0 | 待办 |
| T-11 | 创建首批 `.j2` 模板文件（vector/raster/general 各至少 1 个） | DC-0050, DC-0053 | P0 | 待办 |
| T-12 | 验证所有注册表模板可成功渲染（冒烟测试） | — | P0 | 待办 |

---

## Phase 4: 质量门禁

| 任务 ID | 任务名称 | 关联设计决策 | 优先级 | 状态 |
|:-------:|---------|:----------:|:------:|:----:|
| T-13 | 运行 `ruff format` + `ruff check` | — | P0 | 待办 |
| T-14 | 运行 `mypy --strict data/templates/` | — | P0 | 待办 |
| T-15 | 运行 `pytest tests/unit/test_templates.py -v --cov` | TDD-5 | P0 | 待办 |

---

## 详细任务说明

### T-01: 创建 `src/core/models.py`

在 `core/` 包下创建基础数据模型，供 templates 模块导入使用。后续 core 模块实现 `TemplateRegistry` 时直接复用。

```python
# core/models.py
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class ParamDef:
    """参数定义（来自模板注册表）。"""
    name: str
    type: str
    required: bool
    description: str
    default: Optional[str] = None


@dataclass(frozen=True)
class TemplateDef:
    """模板定义（来自模板注册表）。"""
    id: str
    name: str
    description: str
    template_file: str
    params: List[ParamDef]
```

同时更新 `core/__init__.py` 暴露这些类型。

---

### T-02: 创建 `data/templates/` 模块骨架

创建以下文件：
- `SourceCode/data/templates/__init__.py`
- `SourceCode/data/templates/engine.py`（TemplateEngine、filter、checker）
- `SourceCode/tests/unit/test_templates.py`

---

### T-03: 编写单元测试（TDD 红阶段）

依据 plan-templates §7.1 测试策略，覆盖以下场景：

| 测试类 | 测试方法 | 验证点 |
|--------|---------|--------|
| `TestRenderedScript` | `test_dataclass_fields` | `RenderedScript` 字段正确 |
| `TestQuoteFilter` | `test_simple_string` | 无特殊字符不转义 |
| `TestQuoteFilter` | `test_space_in_filename` | 含空格文件名被 quote |
| `TestQuoteFilter` | `test_shell_metacharacter` | `;` 被转义 |
| `TestSafePathFilter` | `test_relative_path` | 相对路径解析为 workspace 下绝对路径 |
| `TestSafePathFilter` | `test_absolute_path` | 绝对路径直接使用（v2.0.0 不限制范围） |
| `TestScriptSecurityChecker` | `test_normal_command_passes` | 正常命令通过 |
| `TestScriptSecurityChecker` | `test_semicolon_blocked` | `cmd1; cmd2` 被拦截 |
| `TestScriptSecurityChecker` | `test_command_substitution_blocked` | `$(whoami)` 被拦截 |
| `TestScriptSecurityChecker` | `test_backtick_blocked` | 反引号被拦截 |
| `TestScriptSecurityChecker` | `test_path_traversal_blocked` | `../../etc` 被拦截 |
| `TestTemplateEngineRender` | `test_basic_render_windows` | Windows 平台输出含 `@echo off` |
| `TestTemplateEngineRender` | `test_optional_param_omitted` | 未提供可选参数时条件块不渲染 |
| `TestTemplateEngineRender` | `test_shell_escape` | 含空格文件名被正确 quote |
| `TestTemplateEngineRender` | `test_security_check_blocks_injection` | `; rm -rf` 被 SecurityCheckError 拦截 |
| `TestTemplateEngineRender` | `test_template_not_found` | 注册表指向缺失文件时抛 TemplateNotFoundError |
| `TestTemplateEngineValidate` | `test_missing_required_param` | 必填参数缺失返回错误 |
| `TestTemplateEngineValidate` | `test_whitelist_blocks_illegal` | 含 `;` 的参数被拦截 |

---

### T-04~T-09: 核心实现（TDD 绿阶段）

按 TDD 纪律逐个通过测试：

**T-04 数据模型**:
- `Platform(Enum)`: WINDOWS="windows", UNIX="unix"
- `RenderedScript`: content, command_lines, platform, output_path

**T-05 异常类型**:
- `TemplateError(Exception)`
- `TemplateNotFoundError(TemplateError)`
- `RenderError(TemplateError)`
- `SecurityCheckError(TemplateError)`

**T-06 quote_filter**:
```python
def quote_filter(value: str) -> str:
    return shlex.quote(value)
```

**T-07 safe_path_filter**:
```python
def safe_path_filter(value: str, workspace: Workspace) -> str:
    resolved = workspace.resolve_path(value)
    return str(resolved)
```

**T-08 ScriptSecurityChecker**:
```python
DANGEROUS_PATTERNS = [
    (r'[;&|]', "包含命令分隔符"),
    (r'\$\(', "包含命令替换"),
    (r'`', "包含反引号命令替换"),
    (r'[<>]{2,}', "包含异常重定向"),
    (r'\.\./\.\.', "包含路径遍历"),
]
```

**T-09 TemplateEngine**:
- `__init__(template_dir, workspace)`: 初始化 Jinja2 Environment，注册 `quote` 和 `safe_path` 过滤器
- `render(template_def, params, platform=None)`: 完整渲染流程（参数校验 → 加载模板 → 渲染 → 提取命令行 → 安全校验 → 组装脚本）
- `validate_params_for_template(template_def, params)`: 预校验（必填参数 + 白名单过滤）

**白名单正则**: `^[\w\.\/:@\-=\"\s]+$`

---

### T-10~T-11: 模板文件

**registry.json 结构**:
```json
{
  "templates": [
    {
      "id": "shp2geojson",
      "name": "Shapefile 转 GeoJSON",
      "description": "将 Shapefile 格式转换为 GeoJSON",
      "template_file": "vector/shp2geojson.j2",
      "params": [
        {"name": "input", "type": "file_path", "required": true, "description": "输入 Shapefile 路径"},
        {"name": "output", "type": "file_path", "required": true, "description": "输出 GeoJSON 路径"},
        {"name": "s_srs", "type": "crs", "required": false, "description": "源坐标系 EPSG 代码"},
        {"name": "t_srs", "type": "crs", "required": false, "default": "EPSG:4326", "description": "目标坐标系 EPSG 代码"}
      ]
    }
  ]
}
```

**首批模板**（至少 3 个，覆盖 vector/raster/general）：
- `vector/shp2geojson.j2`: ogr2ogr Shapefile → GeoJSON
- `raster/clip_raster.j2`: gdalwarp 栅格裁剪
- `general/info_query.j2`: gdalinfo / ogrinfo 信息查询

---

### T-12: 冒烟测试

用 mock 参数验证所有注册表中的模板均可成功渲染，不抛异常。

---

### T-13~T-15: 质量门禁

```bash
cd SourceCode
ruff format data/templates/ tests/unit/test_templates.py src/core/models.py
ruff check data/templates/ tests/unit/test_templates.py src/core/models.py
mypy --strict data/templates/ src/core/models.py
pytest tests/unit/test_templates.py -v --cov=src.templates --cov-report=term-missing
```

门禁标准：pytest 全通过，覆盖率 ≥80%。

---

## 需求追溯表

| 需求 ID | 设计决策 | 任务 | 说明 |
|:-------:|:--------:|:----:|------|
| F4 | DC-0050, DC-0054 | T-09, T-11 | Jinja2 模板渲染生成脚本 |
| P1 | DC-0050, DC-0053 | T-09, T-11 | 模板化命令，禁止字符串拼接 |
| P2 | DC-0054 | T-09 | 完整脚本展示 |
| P3 | DC-0050 | T-11 | 模板中使用时间戳路径 |
| CODE-1 | DC-0050 | T-09, T-11 | 所有命令来自 `data/templates/` |
| CODE-6 | DC-0051, DC-0053 | T-06, T-07 | 参数转义 |
| SEC-5 | DC-0052 | T-08 | 渲染后二次校验 |
| CODE-2 | DC-0053 | T-07 | safe_path 路径规范化 |
