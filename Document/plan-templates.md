# plan-templates

| 项目 | 内容 |
|------|------|
| 版本 | v1.0.1 |
| 状态 | 设计基线 |
| 作者 | - |
| 日期 | 2026-05-28 |

---

## 1. 设计概述

### 1.1 模块职责

管理 GIS Agent 的 Jinja2 模板引擎：模板文件组织、参数渲染、输出脚本生成、渲染后命令的安全校验。本模块是**"模板化命令，杜绝幻觉"（P1）的核心实现**，确保所有 GDAL 命令均来自预定义的模板，严禁动态字符串拼接。

### 1.2 所属架构层次

核心层（`core/` 的子模块，逻辑上归属核心层）。被 CLI 层调用，依赖 workspace 层进行路径解析。

### 1.3 对应需求项

| 需求 ID | 需求描述 |
|:-------:|---------|
| F4 | 根据模板 + 参数，使用 Jinja2 渲染生成可执行的批处理脚本 |
| P1 | 所有 GDAL 命令必须通过 Jinja2 模板渲染生成，严禁动态字符串拼接 |
| P2 | 向用户完整展示脚本内容，获得明确确认后才执行 |
| P3 | 输出文件默认加时间戳防覆盖 |
| CODE-1 | 所有 GDAL 命令字符串必须通过 `data/templates/` 下的 Jinja2 模板渲染 |
| CODE-6 | 模板文件 (*.j2) 中的参数必须做转义处理 |
| F1 | 文档问答：基于模板元数据回答用户问题 |
| SEC-5 | 模板渲染后的命令字符串必须经安全校验层二次检查后方可提交执行 |

---

## 2. 设计决策

### DC-0050: 模板文件按功能域子目录组织

**决策**: 模板文件（*.j2）存放于 `SourceCode/data/templates/`，按 `vector/`、`raster/`、`general/` 子目录分类。Python 源码（engine.py、__init__.py）保留在 `SourceCode/src/templates/`。

**理由**:
- GDAL 工具天然分为矢量处理（ogr2ogr 等）和栅格处理（gdalwarp 等）
- 子目录便于模板管理和导航
- `.j2` 文件头部用注释声明元数据，模板体使用相对路径（如 `"vector/shp2geojson.j2"`）

**目录结构**:
```
SourceCode/data/templates/      # 模板数据（用户可扩展）
├── vector/
│   ├── shp2geojson.j2          # 注释头自描述：@id, @name, @param
│   ├── merge_shp.j2
│   └── shp_reproject.j2
├── raster/
│   ├── warp_reproject.j2
│   ├── translate_format.j2
│   └── clip_raster.j2
└── general/
    └── info_query.j2

SourceCode/src/templates/       # Python 源码
├── __init__.py
├── engine.py                   # TemplateEngine
└── scanner.py                  # scan_templates(), parse_j2_header()
```

### DC-0051: 参数转义采用"白名单 + shell 转义"双层策略

**决策**: 所有注入模板的参数值在渲染前经过两层处理：
1. **白名单过滤**：参数值只能包含允许字符（字母、数字、下划线、点、斜杠、冒号、连字符、等号、引号、空格）
2. **Shell 转义**：使用 `shlex.quote()`（Unix）或双引号包裹（Windows）对最终命令中的字符串参数进行 shell 安全转义

**理由**:
- 白名单从源头阻止注入字符（如 `;`、`&`、`|`、`$()`）
- Unix 使用 `shlex.quote()` 对 shell 元字符提供完整保护
- Windows 使用双引号包裹（cmd 不支持单引号字符串），配合白名单已拦截危险字符
- 双层策略即使白名单有遗漏，shell 转义仍能兜底

**允许字符正则**:
```python
# 白名单：字母数字 + 常用路径/参数字符 + 引号空格
ALLOWED_PATTERN = re.compile(r'^[\w\./:@\-="\s]+$')
```

### DC-0052: 渲染后的命令字符串经安全校验层二次检查

**决策**: 模板渲染完成后、展示给用户前，对生成的命令字符串进行正则模式匹配，检测是否包含危险字符或命令拼接痕迹。

**理由**:
- 纵深防御：即使模板本身被篡改，二次校验可拦截异常输出
- 符合 SEC-5 要求
- 检查规则可独立维护，不依赖模板实现

**校验规则**:
| 规则 | 模式 | 说明 |
|------|------|------|
| 禁止命令分隔符 | `[;&|]` | 防止 `cmd1; cmd2` 或 `cmd1 \|\| cmd2` |
| 禁止命令替换 | `\$\(` 或 `` ` `` | 防止 `$(whoami)` |
| 禁止重定向滥用 | `[<>]{2,}` | 防止 `>>/etc/passwd` |
| 禁止路径遍历 | `\.\./\.\.` | 防止 `../../etc`（Workspace 已处理，二次保险） |

### DC-0053: 模板内参数使用显式过滤器语法

**决策**: 模板中所有用户输入参数必须通过 `\| quote` 或 `\| safe_path` 过滤器显式声明转义方式。

**理由**:
- 强制开发者显式考虑每个参数的转义需求
- Jinja2 的过滤器语法天然适合此场景
- 代码审查时可直接 grep `\| quote` 检查是否遗漏

**模板示例**:
```jinja2
{# vector/shp2geojson.j2 #}
ogr2ogr -f "GeoJSON" {{ output | quote }} {{ input | quote }}
{% if t_srs %}-t_srs {{ t_srs | quote }}{% endif %}
```

### DC-0054: 输出脚本按目标平台生成对应格式

**决策**: 渲染时根据目标平台（Windows/Unix）生成 `.bat` 或 `.sh` 脚本，并自动添加对应平台的 shebang/echo 头。

**理由**:
- 团队内可能同时使用 Windows 和 Linux
- GDAL CLI 命令本身跨平台，但脚本语法不同
- 默认使用当前运行平台，支持 `--platform` 参数覆盖

### DC-0055: 模板注释头扩展为知识元数据载体

**决策**: `.j2` 模板注释头在现有 `@id`、`@name`、`@description`、`@param` 基础上，新增 `@concept`、`@note`、`@seealso`、`@common_error` 四种元数据标签。扫描器负责解析并注入 `TemplateDef` 的扩展字段。

**标签格式**:

| 标签 | 语法 | 用途 | 出现次数 |
|------|------|------|---------|
| `@concept` | `{# @concept "术语" — 解释文本 #}` | 定义模板涉及的基础概念 | 0-N |
| `@note` | `{# @note 提示文本 #}` | 使用前提、注意事项 | 0-N |
| `@seealso` | `{# @seealso template_id #}` | 关联相关模板 ID | 0-N |
| `@common_error` | `{# @common_error "错误文本" — 原因与修复 #}` | 记录典型错误及处理 | 0-N |

**示例**:
```jinja2
{# @id raster/reproject #}
{# @name 栅格重投影 #}
{# @description 使用 gdalwarp 对栅格数据进行坐标系转换 #}
{# @concept "重采样" — 改变像素网格时计算新像素值的方法 #}
{# @note 如果源数据没有坐标系，需要先使用 gdal_edit 添加 #}
{# @seealso raster/translate_format #}
{# @common_error "ERROR 6: No coordinate system" — 输入文件缺少坐标系，需先添加 #}
{# @param input file_path required 输入栅格文件 #}
{# @param output file_path required 输出路径 #}
```

**理由**:
- 模板同时是可执行脚本和结构化知识卡片，知识与行动同源
- 注释格式与现有 `@param` 语法一致，扫描器可统一解析
- 人工编码的知识质量高于自动解析的 HTML chunks

**扫描器扩展**:
- `parse_j2_header()` 新增对上述四种标签的正则匹配
- 解析结果存入 `TemplateDef` 的扩展字段：`concepts`、`notes`、`seealso`、`common_errors`
- 未知标签忽略（向前兼容）

---

## 3. 接口定义

### 3.1 数据模型

```python
from dataclasses import dataclass
from enum import Enum
from typing import Dict


class Platform(Enum):
    """目标平台。"""
    WINDOWS = "windows"
    UNIX = "unix"


@dataclass(frozen=True)
class RenderedScript:
    """渲染后的脚本。"""
    content: str              # 完整脚本内容
    command_lines: list[str]  # 提取出的 GDAL 命令行（用于单独展示）
    platform: Platform        # 目标平台
    output_path: str          # 建议的脚本保存路径
```

### 3.2 异常类型

```python
class TemplateError(Exception):
    """模板模块基础异常。"""


class TemplateNotFoundError(TemplateError):
    """模板文件不存在。"""


class RenderError(TemplateError):
    """模板渲染失败（参数缺失、类型错误等）。"""


class SecurityCheckError(TemplateError):
    """渲染后的命令未通过安全校验。"""
```

### 3.3 模板引擎

```python
from pathlib import Path
from typing import Dict, Optional

from core import TemplateDef, Workspace


class TemplateEngine:
    """Jinja2 模板渲染引擎。

    负责模板加载、参数转义、脚本渲染、安全校验。

    Design:
        DC-0050, DC-0051, DC-0052, DC-0053, DC-0054
    """

    def __init__(
        self,
        template_dir: Path,
        workspace: Workspace,
    ) -> None:
        """初始化 Jinja2 环境。

        Args:
            template_dir: 模板数据根目录（`SourceCode/data/templates/`）。
            workspace: 用于 safe_path 过滤器（解析相对路径为绝对路径）。
        """

    def render(
        self,
        template_def: TemplateDef,
        params: Dict[str, str],
        platform: Optional[Platform] = None,
    ) -> RenderedScript:
        """渲染模板生成脚本。

        执行流程：
        1. 校验所有参数通过白名单过滤
        2. 加载模板文件
        3. 使用 Jinja2 渲染（含 quote/safe_path 过滤器）
        4. 提取 GDAL 命令行
        5. 二次安全校验
        6. 组装为平台特定脚本格式

        Args:
            template_def: 模板定义（来自 TemplateRegistry）。
            params: 已校验的参数键值对。
            platform: 目标平台。默认使用当前运行平台。

        Returns:
            渲染后的脚本对象。

        Raises:
            TemplateNotFoundError: 模板文件不存在。
            RenderError: 参数缺失或模板语法错误。
            SecurityCheckError: 渲染结果未通过安全校验。
        """

    def validate_params_for_template(
        self,
        template_def: TemplateDef,
        params: Dict[str, str],
    ) -> tuple[bool, Optional[str]]:
        """预校验参数是否满足模板渲染的基本要求。

        检查项：
        - 所有必填参数已提供
        - 参数值通过白名单过滤
        - file_path 类型参数通过 Workspace 路径校验

        Returns:
            (True, None) 或 (False, error_message)
        """
```

### 3.4 Jinja2 自定义过滤器

```python
def quote_filter(value: str) -> str:
    """Shell 安全转义过滤器。

    Windows: 使用双引号包裹（cmd 不支持单引号字符串）。
    Unix: 使用 shlex.quote() 进行 POSIX 兼容转义。

    示例：
        Windows: {{ "my file.shp" | quote }} → '"my file.shp"'
        Unix:    {{ "my file.shp" | quote }} → "'my file.shp'"
    """


def safe_path_filter(value: str, workspace: Workspace) -> str:
    """安全路径解析过滤器。

    将相对路径解析为工作空间内的绝对路径，
    同时进行路径安全校验。

    示例：
        {{ "data/roads.shp" | safe_path }} → "/workspace/data/roads.shp"
    """
```

### 3.5 安全校验器

```python
class ScriptSecurityChecker:
    """脚本安全校验器。

    对渲染后的命令字符串进行二次安全检查。

    Design:
        DC-0052
    """

    DANGEROUS_PATTERNS = [
        (r'[;&|]', "包含命令分隔符"),
        (r'\$\(', "包含命令替换"),
        (r'`', "包含反引号命令替换"),
        (r'[<>]{2,}', "包含异常重定向"),
        (r'\.\./\.\.', "包含路径遍历"),
    ]

    def check(self, script: str) -> tuple[bool, Optional[str]]:
        """检查脚本是否安全。

        Returns:
            (True, None) 表示通过。
            (False, reason) 表示未通过，reason 为具体原因。
        """
```

---

## 4. 数据流与控制流

### 4.1 模板渲染完整流程

```
[core 层调用 TemplateEngine.render()]
    │
    ▼
参数预校验
    │
    ├──→ 必填参数缺失？→ RenderError("缺少必填参数：xxx")
    │
    ├──→ 参数值含非法字符？→ RenderError("参数 xxx 包含非法字符")
    │
    └──→ file_path 参数路径越界？→ RenderError("路径超出工作空间")
    │
    ▼
加载 Jinja2 模板文件
    │
    ├──→ 文件不存在？→ TemplateNotFoundError
    │
    ▼
渲染模板
    │
    ├──→ 参数通过 quote / safe_path 过滤器处理
    │
    ├──→ 模板语法错误？→ RenderError
    │
    └──→ 生成原始命令字符串
    │
    ▼
提取 GDAL 命令行
    │
    ├──→ 按行解析，识别 ogr2ogr / gdalwarp / gdal_translate 等
    │
    ▼
二次安全校验（ScriptSecurityChecker.check）
    │
    ├──→ 检测到危险模式？→ SecurityCheckError("脚本包含非法字符：xxx")
    │
    ▼
组装平台脚本
    │
    ├──→ Windows: 添加 @echo off 头，生成 .bat
    │    Unix: 添加 #!/bin/bash shebang，生成 .sh
    │
    └──→ 添加注释头（生成时间、模板ID、原始参数）
    │
    ▼
返回 RenderedScript
```

### 4.2 模板文件示例

**`vector/shp2geojson.j2`**:
```jinja2
{# 模板：Shapefile 转 GeoJSON #}
{# 参数：input, output, s_srs, t_srs #}

@echo off
REM Generated by GIS Agent
REM Template: shp2geojson
REM Time: {{ generation_time }}

ogr2ogr -f "GeoJSON" {{ output | safe_path | quote }} {{ input | safe_path | quote }}
{%- if t_srs %} -t_srs {{ t_srs | quote }}{% endif %}
{%- if s_srs %} -s_srs {{ s_srs | quote }}{% endif %}

REM Done
```

**`raster/clip_raster.j2`**:
```jinja2
{# 模板：栅格裁剪 #}
{# 参数：input, output, cutline, crop_to_cutline #}

@echo off
REM Generated by GIS Agent

gdalwarp
  {{ input | safe_path | quote }}
  {{ output | safe_path | quote }}
  -cutline {{ cutline | safe_path | quote }}
  {%- if crop_to_cutline | lower == "true" %} -crop_to_cutline{% endif %}

REM Done
```

### 4.3 渲染输出示例

**输入参数**:
```json
{
  "input": "data/roads.shp",
  "output": "roads_out_20260526_143052.geojson",
  "t_srs": "EPSG:4326"
}
```

**输出脚本（Windows .bat）**:
```batch
@echo off
REM Generated by GIS Agent
REM Template: shp2geojson
REM Time: 2026-05-26 14:30:52

ogr2ogr -f "GeoJSON" 'F:\project\workspace\roads_out_20260526_143052.geojson' 'F:\project\workspace\data\roads.shp' -t_srs 'EPSG:4326'

REM Done
```

---

## 5. 依赖关系

### 5.1 向上依赖

| 模块 | 接口 | 用途 |
|------|------|------|
| `core` (TemplateRegistry) | `TemplateDef` | 获取模板文件路径和参数定义 |
| `workspace` | `Workspace.resolve_path()` | `safe_path` 过滤器 |
| `config` | `get_config()` | 平台配置 |

### 5.2 向下暴露

| 接口 | 使用方 |
|------|--------|
| `TemplateEngine.render()` | `core/`（`SessionProcessor` 在 SCRIPT_PREVIEW 状态时调用） |
| `TemplateEngine.validate_params_for_template()` | `core/`（`ParamValidator` 调用） |
| `RenderedScript` | `cli/`（展示给用户并保存到文件） |

### 5.3 外部依赖

| 库 | 用途 | 约束 |
|---|------|------|
| `jinja2` | 模板渲染引擎 | P5 已锁定 |
| `shlex` | Shell 转义 | Python 标准库 |

---

## 6. 异常与错误处理

| 异常类型 | 触发条件 | 处理策略 |
|---------|---------|---------|
| `TemplateNotFoundError` | 扫描器记录的 `template_file` 路径不存在 | 内部错误（.j2 文件被删除但扫描缓存未更新），记录 ERROR 并提示"模板加载失败" |
| `RenderError` | 参数缺失、模板语法错误 | 向用户展示具体错误，返回 PARAM_COLLECT 状态 |
| `SecurityCheckError` | 渲染结果含危险字符 | 记录 ERROR（含原始参数用于审计），向用户展示"脚本生成异常，请检查参数" |
| `jinja2.TemplateError` | Jinja2 内部错误 | 包装为 RenderError 后向上抛 |

---

## 7. 测试策略

### 7.1 单元测试覆盖

| 测试场景 | 验证点 |
|---------|--------|
| 正常渲染 | 输入合法参数，输出正确命令行 |
| 可选参数省略 | 未提供可选参数时，条件块不渲染 |
| 路径参数解析 | `safe_path` 正确解析为绝对路径 |
| Shell 转义 | 含空格的文件名被正确 quote |
| 白名单过滤 | 含 `;` 的参数被拦截 |
| 安全校验通过 | 正常命令通过二次校验 |
| 安全校验拦截 | 注入 `; rm -rf /` 被 SecurityCheckError 拦截 |
| 平台格式 | Windows 输出含 `@echo off`，Unix 含 shebang |
| 模板不存在 | 扫描结果指向缺失文件时抛 TemplateNotFoundError |

### 7.2 集成测试场景

- 端到端渲染：扫描器 → 模板加载 → 参数渲染 → 安全校验 → 输出脚本
- 所有扫描发现的模板均可成功渲染（用 mock 参数冒烟测试）

### 7.3 Mock 策略

- `Workspace` mock：固定根目录 `/tmp/test_workspace/`
- 使用内存中的临时 `.j2` 文件（不依赖真实模板目录）
- `shlex.quote` 无需 mock（标准库，行为确定）

---

## 8. 需求追溯表

| 需求 ID | 设计决策 | 代码文件/函数 | 说明 |
|:-------:|:--------:|:-------------:|------|
| F1 | DC-0055 | `parse_j2_header()` 扩展标签解析 | 模板元数据作为问答知识源 |
| F4 | DC-0050, DC-0054 | `TemplateEngine.render()` | Jinja2 模板渲染生成脚本 |
| P1 | DC-0050, DC-0053 | 模板扫描器 + Jinja2 过滤器 | 模板化命令，禁止字符串拼接 |
| P2 | DC-0054 | `RenderedScript.content` | 完整脚本展示 |
| P3 | DC-0050 | 模板中使用时间戳路径 | 输出文件防覆盖 |
| CODE-1 | DC-0050 | 模板目录结构 | 所有命令来自 `data/templates/` |
| CODE-6 | DC-0051, DC-0053 | `quote_filter`, `safe_path_filter` | 参数转义 |
| SEC-5 | DC-0052 | `ScriptSecurityChecker.check()` | 渲染后二次校验 |
| CODE-2 | DC-0053 | `safe_path_filter` | 路径安全校验 |

---

## 附录：变更记录
architecture-diagram.htmlarchitecture-diagram.h
| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.1.0 | 2026-05-28 | 新增 DC-0055：模板注释头扩展为知识元数据载体，新增 `@concept`、`@note`、`@seealso`、`@common_error` 标签；更新需求追溯表 |
| v1.0.1 | 2026-05-28 | quote_filter Windows 兼容：Windows 平台使用双引号包裹（cmd 不支持单引号字符串），Unix 仍使用 shlex.quote |
| v1.0.0 | 2026-05-26 | 初版，定义模板目录结构、Jinja2 渲染、参数转义、安全校验、跨平台脚本生成 |
