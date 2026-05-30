# plan-j2-generate

| 项目 | 内容 |
|------|------|
| 版本 | v2.0.0 |
| 状态 | 草案 |
| 作者 | - |
| 日期 | 2026-05-30 |

---

## 1. 设计概述

### 1.1 模块职责

J2 模板生成器提供**双模式**的模板生产能力，将 GDAL/HTML 文档转换为 GIS Agent 可用的 Jinja2 模板（`*.j2`）：

| 模式 | 使用场景 | 入口 | 使用者 |
|------|---------|------|--------|
| **在线交互模式** | 单模板实时生成、调试、迭代 | Agent 前端 `/generator` 页面 | 终端用户/开发者 |
| **CLI 批量模式** | 批量处理 GDAL HTML 文档库，扩充模板库 | `scripts/generate_templates.py` | 开发者 |

两种模式**复用相同的底层 LLM 生成/审核/渲染逻辑**，差异仅在于输入来源（单文档粘贴 vs 批量目录扫描）和交互方式（可视化向导 vs 命令行）。

### 1.2 所属架构层次

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              双模式入口层                                     │
│  ┌──────────────────────┐                    ┌──────────────────────────┐   │
│  │ 在线交互模式          │                    │ CLI 批量模式 (开发时)     │   │
│  │ frontend/GeneratorPage│                    │ scripts/generate/*.py    │   │
│  │ api/routes/generator.py│                   │ scripts/generate_templates.py││
│  └──────────┬───────────┘                    └────────────┬─────────────┘   │
│             │ HTTP /api/generator/*                        │ 直接 import    │
│             ▼                                              ▼                │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                        共享核心逻辑层                                  │   │
│  │  llm.client.LLMClient — LLM API 调用（含重试、截断）                    │   │
│  │  templates.engine.ScriptSecurityChecker — 渲染后安全校验               │   │
│  │  templates.scanner.scan_templates — 生成后验证可扫描性                 │   │
│  │  rag.preprocess._GDALDocParser — HTML 结构化提取（批量模式）            │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

- **在线模式**：属于 `api/` + `frontend/` 架构层，运行时可用
- **CLI 批量模式**：属于 `scripts/` 开发工具层，不进入生产运行时（DC-0080）

### 1.3 对应需求项

| 需求 ID | 需求描述 |
|:-------:|---------|
| P1 | 所有 GDAL 命令必须通过 J2 模板渲染，本模块是模板库的生产手段 |
| P4 | 模板元数据（`@param`、`@concept` 等）必须完整准确 |
| P5 | 复用现有 anthropic/jinja2 依赖，不引入新生产依赖 |
| UX-3 | J2 模板生成器：文档输入 → LLM 生成 → 审查 → 保存 |

---

## 2. 设计决策

### DC-0080: 双模式并存——在线交互 + CLI 批量

**决策**: 模板生成器同时支持两种模式：
1. **在线交互模式**：Agent 前端 `/generator` 页面，单文档实时生成、可视化审查、一键保存
2. **CLI 批量模式**：`scripts/generate_templates.py`，批量目录扫描、断点续传、审核队列

**理由**:
- 在线模式降低模板创作门槛：用户无需命令行知识，粘贴文档即可生成可用模板
- CLI 批量模式保留开发效率：扩充模板库时仍可用脚本批量处理
- 两种模式底层逻辑统一（DC-0090），维护成本不增加

**目录定位**:
```
# 在线模式（运行时）
SourceCode/src/api/routes/generator.py      # REST API
SourceCode/frontend/src/pages/GeneratorPage.tsx  # 前端页面
SourceCode/frontend/src/api/generator.ts    # 前端 API 客户端

# CLI 批量模式（开发时）
SourceCode/scripts/generate_templates.py    # 主 CLI 入口
SourceCode/scripts/generate/                # 批量工具内部模块
```

### DC-UX-07: 模板生成器作为独立子页面

**决策**: J2 模板生成器不集成在主应用会话状态机中，而是作为独立路由 `/generator`，通过导航栏入口进入，完成后返回主应用。

**理由**:
- 模板生成是低频辅助功能，使用频率远低于主任务流程
- 独立页面避免干扰主应用 `Session` 状态管理（IDLE → INTENT_CONFIRM → ... 状态机）
- 生成器有自己的五步向导（文档输入 → 配置 → 预览 → 编辑审查 → 保存），不适合塞进主状态机
- 保存成功后，模板自动进入 `TemplateRegistry`，主应用无需重启即可使用

### DC-0081: 双阶段 LLM 流程（生成 → 审核）

**决策**: 每个文档经历两个独立的 LLM 调用：
1. **生成阶段**：LLM 根据文档文本，输出结构化的 `TemplateDefinition`（JSON）
2. **审核阶段**：另一个 LLM 调用（或同一模型不同 prompt）对 `TemplateDefinition` 进行质量检查

**理由**:
- 生成与审核解耦，便于独立迭代 prompt
- 审核可作为质量门禁，拦截明显错误（参数类型不匹配、命令语法错误）
- 两阶段均失败时进入人工审核队列（批量模式）或前端展示错误（在线模式），不直接丢弃

**流程图（批量模式）**:
```
HTML 文件
    │
    ▼
┌─────────────────┐
│  HTML Parser    │  ← 复用 _GDALDocParser
│  (提取文本)     │
└────────┬────────┘
         ▼
┌─────────────────┐     失败 ──→ 人工审核队列
│  LLM 生成       │  ──────────→ (reason: 无法解析)
│  TemplateDef    │
└────────┬────────┘
         │ 输出 JSON
         ▼
┌─────────────────┐     失败 ──→ 人工审核队列
│  LLM 审核       │  ──────────→ (reason: 审核不通过)
│  (质量检查)     │
└────────┬────────┘
         │ 审核通过
         ▼
┌─────────────────┐     失败 ──→ 人工审核队列
│  J2 渲染        │  ──────────→ (reason: 语法错误/安全校验失败)
│  + 安全校验     │
└────────┬────────┘
         ▼
    输出 .j2 文件
```

**流程图（在线模式）**:
```
用户粘贴文档 ──→ LLM 生成 ──→ 前端预览 ──→ 用户编辑/审查 ──→ 安全校验 ──→ 保存
                     │              │              │
                     ▼              ▼              ▼
                  JSON 解析失败   用户可编辑      校验失败
                  前端展示错误    调整参数/模板    前端展示错误
```

在线模式将 LLM 审核阶段替换为**用户人工审查 + 自动安全校验**，赋予用户更大的控制权。

### DC-0090: 底层 LLM 逻辑复用

**决策**: 在线模式和 CLI 批量模式共用相同的 prompt 构建、JSON 解析、J2 渲染逻辑。在线模式的 API 路由直接调用这些共享函数，而非重写。

**理由**:
- 避免 prompt 在两个地方维护导致漂移
- 生成质量一致：在线用户和批量脚本使用相同的 LLM 策略
- 统一错误处理：JSON 解析失败、安全校验失败等异常处理逻辑一致

**共享逻辑清单**:
| 逻辑 | 在线模式调用 | CLI 批量模式调用 |
|------|------------|-----------------|
| Prompt 构建 | `_build_generate_prompt()` | `generator.py::build_prompt()` |
| JSON 解析 | `_parse_generated_response()` | `models.py::from_llm_output()` |
| Jinja2 语法校验 | `_validate_jinja2_syntax()` | `renderer.py::render()` |
| 安全校验 | `ScriptSecurityChecker.check()` | `ScriptSecurityChecker.check()` |
| 模板扫描验证 | `scan_templates()` | `scan_templates()` |

### DC-0082: JSON Schema 中间表示

**决策**: LLM 输出必须是符合预定义 JSON Schema 的结构化数据，不直接输出 J2 文本。

**理由**:
- 结构化数据便于程序校验（必填字段、类型检查、默认值合法性）
- 审核阶段可对结构化数据做规则校验（如参数名是否在命令模板中出现）
- 与 J2 渲染解耦，允许在不改动 LLM prompt 的情况下调整输出格式

**Schema 定义**（`TemplateDefinition`）:
```json
{
  "id": "ogr2ogr_to_geojson",
  "name": "矢量格式转换",
  "description": "使用 ogr2ogr 将矢量数据从一种格式转换为另一种格式",
  "category": "vector",
  "command_template": "ogr2ogr -f {{ format | quote }} {{ output | quote }} {{ input | quote }}",
  "params": [
    {
      "name": "input",
      "type": "file_path",
      "required": true,
      "description": "输入矢量文件路径"
    },
    {
      "name": "output",
      "type": "file_path",
      "required": true,
      "description": "输出文件路径"
    },
    {
      "name": "format",
      "type": "string",
      "required": false,
      "default": "GeoJSON",
      "description": "目标格式名称"
    },
    {
      "name": "t_srs",
      "type": "crs",
      "required": false,
      "description": "目标坐标系"
    }
  ],
  "concepts": ["ogr2ogr 是 GDAL 的矢量格式转换工具"],
  "notes": ["输出文件若已存在会被覆盖"],
  "common_errors": [
    {
      "error_text": "Unable to open datasource",
      "explanation": "输入文件路径错误或文件不存在"
    }
  ]
}
```

**字段约束**:
| 字段 | 类型 | 约束 |
|------|------|------|
| `id` | string | `[a-z0-9_]+`，全局唯一 |
| `name` | string | 中文，2-30 字符 |
| `category` | string | `vector` / `raster` / `general` / `database` |
| `command_template` | string | 必须包含 Jinja2 `{{ }}` 变量，且所有参数名均须在模板中出现 |
| `params[].type` | string | 枚举: `file_path`, `crs`, `string`, `boolean`, `integer`, `float` |
| `params[].required` | boolean | 必填参数不允许有 `default` |

### DC-0091: 在线模式支持模板实时编辑

**决策**: 在线模式在"预览"阶段提供模板体编辑器，允许用户在 LLM 生成的基础上手动修改模板内容，修改后重新触发安全校验。

**理由**:
- LLM 生成的模板并非 100% 正确，用户需要微调能力
- 实时编辑 + 即时校验的反馈循环，比"生成 → 失败 → 重新粘贴文档"更高效
- 编辑后的模板经过同样的安全校验后才能保存，保证质量

**前端交互流程**:
```
Step 3 预览 ──→ 用户点击"编辑" ──→ 展开代码编辑器 ──→ 修改模板体
                                              │
                                              ▼
                                        点击"重新校验"
                                              │
                                    ┌─────────┴─────────┐
                                    ▼                   ▼
                              校验通过              校验失败
                                    │                   │
                                    ▼                   ▼
                              显示"保存"按钮          展示错误列表
                                    │                   │
                                    ▼                   ▼
                              进入 Step 4           继续编辑
```

### DC-0092: 模板按分类目录存储

**决策**: 保存模板时，根据 `category` 字段自动归类到 `data/templates/{category}/` 子目录。若分类目录不存在则自动创建。

**理由**:
- 与现有模板目录结构一致（`vector/`, `raster/`, `general/`）
- `TemplateRegistry.scan_templates()` 递归扫描子目录，自动识别新分类
- 避免所有模板堆积在根目录，便于管理和浏览

**存储规则**:
```
data/templates/
├── vector/
│   ├── ogr2ogr_reproject.j2
│   └── ...
├── raster/
│   ├── gdalwarp_clip.j2
│   └── ...
├── general/
│   └── ...
└── database/      ← 新增分类自动创建
    └── ogr2ogr_pg_import.j2
```

### DC-0093: 保存后自动热加载

**决策**: 模板保存成功后，自动触发 `TemplateRegistry.rescan()`，使新模板立即可用于主应用的模板选择和意图匹配，无需重启服务。

**理由**:
- 在线模式的核心价值是"即时可用"——生成后立即可以测试
- 用户体验：保存 → 返回主应用 → 新模板已出现在模板列表中
- 避免用户因"找不到刚保存的模板"而困惑

**实现方式**:
- `POST /generator/save` 成功后，调用 `refresh_registry()`（plan-core DC-0095）
- `TemplateRegistry.rescan()` 重新执行 `scan_templates()`，原子替换内存索引
- 前端保存成功后显示提示："模板已保存，返回主应用即可使用"

**依赖**: plan-core DC-0095（`TemplateRegistry.rescan()` 运行时重扫描）

### DC-0083: 人工审核队列机制（CLI 批量模式）

**决策**: CLI 批量模式下，任一阶段失败的 HTML 文件不直接丢弃，而是输出到人工审核队列（JSONL 文件），包含失败原因和原始 LLM 输出，供开发者手动修正后重新提交。

**理由**:
- LLM 不是 100% 可靠，某些复杂的 GDAL 命令格式可能无法正确解析
- 人工修正后的案例可用于 few-shot prompt 优化，形成正向循环
- 不丢失任何输入，确保批量处理的可追溯性

**队列文件格式**（JSON Lines）:
```json
{"source_html": "programs/ogr2ogr.html", "stage": "generation", "reason": "无法从 Synopsis 提取命令骨架", "raw_llm_output": "...", "extracted_text": "...", "timestamp": "2026-05-29T10:00:00Z"}
{"source_html": "drivers/gpkg.html", "stage": "review", "reason": "审核发现参数 'layer' 类型推断错误（应为 string 而非 file_path）", "template_def": {...}, "timestamp": "2026-05-29T10:05:00Z"}
```

### DC-0084: 批量处理与断点续传（CLI 模式）

**决策**: CLI 批量模式支持批量目录扫描，已处理且通过的 HTML 文件跳过（基于输出文件存在性 + 内容哈希），支持中断后恢复。

**理由**:
- 批量处理可能耗时较长（LLM API 调用有延迟）
- 避免重复消费 token
- 便于增量更新（GDAL 文档更新后只处理变更文件）

**状态跟踪**:
- 在输出目录下生成 `.generate_state.json`，记录已处理的 `(source_path, content_hash, output_path, status)`
- 启动时加载状态文件，跳过 `status == "success"` 且哈希未变的条目

### DC-0085: LLM 生成 Prompt 设计

**决策**: 生成阶段采用 few-shot prompt，提供 2-3 个 GDAL 工具（简单、中等、复杂）的文档提取文本 → TemplateDefinition 示例。

**Prompt 结构**:
```
System: 你是一名 GDAL 命令行专家。根据提供的文档提取信息，生成 GIS Agent 使用的 Jinja2 模板定义。

规则：
1. id 使用小写 + 下划线，全局唯一
2. command_template 使用 Jinja2 {{ param_name }} 语法，路径参数用 | quote 过滤
3. 参数类型推断：文件路径 → file_path，坐标系 → crs，开关选项 → boolean，数值 → integer/float，其他 → string
4. [方括号] 包裹的参数为 optional，<> 包裹的为 required
5. 必须包含 @concept（核心概念解释）、@note（使用注意事项）
6. common_errors 从文档的注意事项/已知问题中提取

示例 1: [ogrinfo 简单示例]
示例 2: [ogr2ogr 中等示例]
示例 3: [gdalwarp 复杂示例]

现在处理以下 GDAL 工具文档：
---
[提取的文档文本]
---

输出严格 JSON，不要 markdown 代码块，不要额外解释。
```

### DC-0086: LLM 审核 Prompt 设计（CLI 模式）

**决策**: CLI 批量模式的审核阶段采用检查清单（checklist）形式的 prompt，要求 LLM 逐项检查并给出通过/不通过判定。

**审核检查项**:
1. `id` 是否符合 `[a-z0-9_]+`，是否与现有模板重复
2. `command_template` 是否为有效的 Jinja2 语法，是否包含未声明的变量
3. `command_template` 是否使用 `quote` 过滤所有路径/字符串参数
4. 所有 `params[].name` 是否在 `command_template` 中出现
5. 参数类型推断是否合理（如 `-t_srs` 应为 `crs` 而非 `string`）
6. `required: false` 的参数是否有合理的 `default`
7. `common_errors` 是否与文档描述匹配，非臆造
8. 命令是否使用了危险的 shell 模式（如 `;`, `|`, `$()`）

**审核输出格式**:
```json
{
  "passed": false,
  "issues": [
    {"item": 5, "severity": "error", "message": "参数 't_srs' 类型应为 'crs'，当前为 'string'"},
    {"item": 3, "severity": "warning", "message": "参数 'output' 在 command_template 中未使用 | quote 过滤"}
  ],
  "suggested_fix": {
    "params": [{"name": "t_srs", "type": "crs"}],
    "command_template": "ogr2ogr -f {{ format | quote }} {{ output | quote }} {{ input | quote }}"
  }
}
```

### DC-0087: 审核通过标准（CLI 模式）

**决策**: CLI 批量模式的审核结果分级处理：
- `error` 级别 issue 存在 → 不通过，进入人工审核队列
- 只有 `warning` 级别 issue → 根据配置选择"自动修复后通过"或"进入人工队列"
- 无任何 issue → 直接通过

### DC-0088: 提取器接口抽象，预留通用文档输入

**决策**: `HtmlExtractor` 不直接耦合 GDAL HTML 结构，而是输出一个通用的 `ExtractedDoc` 结构（含 title、synopsis、description、options 列表）。当前实现针对 GDAL Sphinx HTML，但接口设计允许未来接入 Markdown、man page 等其他文档格式。

**理由**:
- 用户扩展 J2 功能需要提供通用入口：用户上传任意工具的 HTML/Markdown 文档，工具分析后生成 J2
- `ExtractedDoc` 作为 LLM 生成阶段的统一输入，屏蔽底层文档格式差异
- 未来只需新增 Extractor 实现（如 `MarkdownExtractor`），无需改动生成/审核/渲染逻辑

**ExtractedDoc 结构**:
```python
@dataclass
class ExtractedDoc:
    title: str           # 工具名称
    synopsis: str        # 命令用法摘要（可选）
    description: str     # 功能描述
    options: list[dict]  # 参数列表，每项含 name、description、required_hint
```

**预留扩展点**:
```
                  ┌─ GDALHtmlExtractor (当前)
用户文档 ──→ Extractor Interface ──┤
                  └─ MarkdownExtractor (预留)
                           │
                           ▼
                    ExtractedDoc ──→ LLMGenerator
```

---

## 3. 接口设计

### 3.1 在线模式 API

#### `POST /api/generator/generate`

从文档文本生成 J2 模板。

**Request**:
```json
{
  "document_text": "ogr2ogr -f format dst_datasource src_datasource...",
  "config": {
    "category": "vector",
    "tool_source": "GDAL"
  }
}
```

**Response**:
```json
{
  "template_id": "ogr2ogr_convert",
  "name": "矢量格式转换",
  "description": "使用 ogr2ogr 将矢量数据转换为指定格式",
  "body": "{# @id ogr2ogr_convert #}\n{# @name ... #}\n...",
  "params": [
    {"name": "input", "type": "file_path", "required": true},
    {"name": "output", "type": "file_path", "required": true},
    {"name": "format", "type": "string", "required": false}
  ],
  "concepts": ["ogr2ogr 是 GDAL 矢量格式转换工具"],
  "notes": ["输出文件若已存在会被覆盖"]
}
```

**错误处理**:
- `400` — `document_text` 为空
- `500` — LLM 调用失败或 JSON 解析失败

#### `POST /api/generator/validate`

对模板体进行安全扫描和 Jinja2 语法校验。

**Request**:
```json
{
  "body": "{# @id test #}\nogr2ogr {{ output | quote }}..."
}
```

**Response**:
```json
{
  "valid": false,
  "errors": [
    "Security check failed: Detected dangerous pattern: ;",
    "Jinja2 syntax error at line 3: unexpected end of template"
  ]
}
```

#### `POST /api/generator/save`

保存审查通过的模板到 `data/templates/{category}/` 目录，保存后自动触发注册表重扫描。

**Request**:
```json
{
  "template_id": "ogr2ogr_convert",
  "body": "...",
  "overwrite": false
}
```

**Response**:
```json
{
  "saved_path": "data/templates/vector/ogr2ogr_convert.j2"
}
```

**错误处理**:
- `409` — 模板已存在且 `overwrite=false`

### 3.2 CLI 批量模式主入口函数

```python
def generate_templates(
    source_dir: Path,
    output_dir: Path,
    *,
    llm_client: LLMClient,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    review_strictness: Literal["strict", "lenient"] = "strict",
    auto_fix_warnings: bool = False,
    max_workers: int = 1,
    dry_run: bool = False,
) -> GenerationReport:
    """批量将 GDAL HTML 文档转换为 J2 模板。

    Design: DC-0080, DC-0081, DC-0084
    """
```

**返回值**:
```python
@dataclass
class GenerationReport:
    total: int              # 处理的 HTML 文件总数
    success: int            # 成功生成并通过审核的模板数
    failed_generation: int  # LLM 生成失败数
    failed_review: int      # 审核不通过数
    failed_render: int      # J2 渲染/安全校验失败数
    skipped: int            # 已存在且未变更的跳过数
    review_queue_path: Path # 人工审核队列文件路径
    output_files: list[Path] # 成功生成的 .j2 文件路径列表
```

### 3.3 CLI 参数

```bash
python scripts/generate_templates.py \
  --source Document/Resource/gdal/build/doc/build/html/programs \
  --output SourceCode/data/templates/ \
  --config SourceCode/config/config.json \
  --strict \
  --max-workers 3
```

| 参数 | 说明 |
|------|------|
| `--source` | GDAL HTML 文档目录 |
| `--output` | J2 模板输出目录 |
| `--config` | 配置文件路径（读取 LLM API 密钥） |
| `--strict` | 严格模式：任何 warning 也视为不通过 |
| `--lenient` | 宽松模式：仅 error 视为不通过，warning 自动修复 |
| `--max-workers` | 并发 LLM 调用数（建议 1-3，受 API 速率限制） |
| `--dry-run` | 空跑：执行全流程但不写入文件 |
| `--force` | 强制重新处理所有文件（忽略状态缓存） |

---

## 4. 前端交互设计

### 4.1 页面结构

`GeneratorPage.tsx` 作为独立页面，通过左侧导航栏"模板生成器"入口进入。

**布局**:
```
┌──────────────────────────────────────────────────────────────┐
│  J2 模板生成器                              [返回主应用]      │
├──────────────────────────────────────────────────────────────┤
│  [1 文档] ── [2 配置] ── [3 预览] ── [4 审查] ── [5 保存]     │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Step 内容区域（根据当前步骤动态切换）                 │   │
│  │                                                      │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 五步向导

| 步骤 | 标题 | 内容 | 操作 |
|------|------|------|------|
| **1** | 输入文档 | 大文本框，粘贴 GDAL HTML 文档或命令说明 | 下一步 |
| **2** | 配置属性 | 分类选择（vector/raster/general/database）、工具来源输入 | 上一步 / 生成模板 |
| **3** | 预览结果 | 展示生成的模板元数据（ID、名称、参数列表）+ 模板体代码预览 | 上一步 / 编辑模板 / 安全审查 |
| **4** | 审查结果 | 安全校验结果展示（通过/失败 + 错误列表）。通过时显示保存按钮 | 上一步 / 保存模板 |
| **5** | 保存成功 | 成功提示、保存路径、返回主应用 / 再生成一个 | - |

### 4.3 Step 3 编辑器交互

Step 3（预览）支持两种视图模式：
- **只读预览**：展示 LLM 生成的模板体，代码高亮显示
- **编辑模式**：点击"编辑模板"后展开 Monaco/CodeMirror 风格的代码编辑器，允许修改模板体

编辑后点击"重新校验"触发 `/generator/validate` API，校验通过后才允许进入 Step 4。

### 4.4 保存成功后的引导

Step 5 保存成功后：
1. 显示绿色成功图标 + "模板保存成功"文案
2. 显示完整保存路径
3. 提示"新模板已加入模板库，返回主应用即可使用"
4. 提供两个操作按钮：
   - **返回主应用** — 路由跳转至 `/`
   - **再生成一个** — 重置状态，回到 Step 1

---

## 5. 异常处理

### 5.1 在线模式

| 异常场景 | 处理策略 |
|---------|---------|
| LLM API 调用失败 | 前端展示错误提示，保留用户输入，允许重试 |
| LLM 输出不符合 JSON | 尝试 markdown JSON 剥离，仍失败则前端展示"生成失败，请检查输入文档是否包含足够的命令信息" |
| J2 渲染语法错误 | 前端 Step 4 展示错误详情，提供"返回编辑"按钮 |
| 安全校验发现危险模式 | 前端 Step 4 红色提示，列出具体问题，禁止保存 |
| 模板 ID 已存在 | `409` 响应，前端提示"模板已存在，是否覆盖？"，用户确认后带 `overwrite=true` 重试 |

### 5.2 CLI 批量模式

| 异常场景 | 处理策略 |
|---------|---------|
| LLM API 调用失败（网络/限流） | 复用 LLMClient 的指数退避重试（DC-0034），3 次后标记该文件为失败 |
| LLM 输出不符合 JSON Schema | 尝试 markdown JSON 剥离（复用 diagnosis.py 的 `_strip_markdown_json`），仍失败则记录到审核队列 |
| J2 渲染语法错误 | 记录到审核队列，附原始 TemplateDefinition |
| 安全校验发现危险模式 | 记录到审核队列，标记 severity=critical |
| 输出文件已存在 | 默认跳过（基于状态缓存），`--force` 时覆盖 |
| 磁盘写入失败 | 抛出异常，终止程序 |

---

## 6. 测试策略

### 6.1 在线模式测试

| 测试用例 | 目标 |
|---------|------|
| `test_generator_api_generate` | 验证 `/generator/generate` 能正确调用 LLM 并返回结构化数据 |
| `test_generator_api_validate_pass` | 验证有效模板通过安全校验和语法校验 |
| `test_generator_api_validate_fail_security` | 验证包含危险模式的模板返回 `valid=false` |
| `test_generator_api_save_success` | 验证保存后文件存在且触发注册表重扫描 |
| `test_generator_api_save_conflict` | 验证重复保存返回 `409`，覆盖后成功 |
| `test_generator_api_save_categorized` | 验证模板按 category 保存到子目录 |

### 6.2 CLI 批量模式测试

| 测试用例 | 目标 |
|---------|------|
| `test_html_parser_integration` | 验证 `_GDALDocParser` 能正确提取至少 3 种典型 GDAL 工具的 Synopsis + Options |
| `test_template_def_validation` | 验证 JSON Schema 校验能捕获缺失字段、非法类型、命令模板语法错误 |
| `test_review_checklist_scoring` | 验证审核输出解析：全通过、有 warning、有 error 三种情况 |
| `test_state_file_persistence` | 验证断点续传状态文件的正确读写 |
| `test_render_pipeline` | 验证 TemplateDefinition → J2 文本 → scanner 可正确解析的完整链路 |
| `test_e2e_ogr2ogr` | 使用真实的 `ogr2ogr.html`，验证端到端生成可工作的 J2 模板 |
| `test_e2e_gdalwarp` | 使用真实的 `gdalwarp.html`，验证复杂参数的正确提取 |
| `test_dry_run_no_side_effects` | 验证 `--dry-run` 不修改任何文件 |
| `test_review_queue_format` | 验证审核队列 JSONL 可被人工阅读并手动修正后重新导入 |

---

## 7. 复杂度评估

| 维度 | 评级 | 说明 |
|------|------|------|
| 架构复杂度 | 中 | 双模式共享底层逻辑，Pipeline 模式清晰分离，无循环依赖 |
| LLM Prompt 工程难度 | 中高 | Few-shot 示例需要覆盖典型 GDAL 工具格式；Schema 约束需严格 |
| 前端交互复杂度 | 中 | 五步向导 + 代码编辑器 + 实时校验，状态管理需清晰 |
| 与现有系统集成 | 低-中 | 在线模式需新增 API 路由和前端页面，复用现有模块；CLI 模式仅 import 现有模块 |
| 审核机制设计 | 中 | 在线模式用用户审查 + 自动校验替代 LLM 审核；CLI 模式保留 checklist 审核 |
| 批处理与容错 | 中 | 断点续传、并发控制、失败队列均为常规工程问题 |
| **总体评估** | **中等偏高** | 核心风险在于 LLM 生成质量的不稳定性；工程框架本身不复杂 |

### 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| LLM 对某些 GDAL 工具生成质量差 | 审核队列积压 / 用户反复编辑 | 在线模式提供实时编辑能力；CLI 模式持续积累 few-shot 示例优化 prompt |
| LLM API 成本过高 | 批量处理不可持续 | CLI 模式实现断点续传避免重复；限制 `--max-workers`；在线模式单文档调用量可控 |
| 生成的模板与运行时需求不匹配 | 模板无法使用 | 两种模式均自动运行 `scan_templates()` 验证可解析性；集成测试覆盖 |
| 模板 ID 冲突 | 保存失败 | 在线模式前端实时检查 ID 可用性；CLI 模式审核阶段检查重复 |

---

## 8. 实现任务拆分

### 在线交互模式

| 任务 ID | 内容 | 依赖 | 状态 |
|---------|------|------|------|
| T-GEN-WEB-01 | 实现 `POST /generator/generate` API | T-GEN-01 | ✅ |
| T-GEN-WEB-02 | 实现 `POST /generator/validate` API | - | ✅ |
| T-GEN-WEB-03 | 实现 `POST /generator/save` API（含自动分类存储、热加载） | T-GEN-WEB-02 | ✅ |
| T-GEN-WEB-04 | 前端 `GeneratorPage.tsx` 五步向导页面 | - | ✅ |
| T-GEN-WEB-05 | 前端模板体编辑器（编辑模式 + 重新校验） | T-GEN-WEB-04 | ⬜ |
| T-GEN-WEB-06 | 导航栏集成 GeneratorPage 入口 | - | ✅ |
| T-GEN-WEB-07 | 保存成功后注册表热加载 + 前端提示 | T-GEN-WEB-03 | ⬜ |

### CLI 批量模式

| 任务 ID | 内容 | 依赖 | 状态 |
|---------|------|------|------|
| T-GEN-01 | 实现 `TemplateDefinition` dataclass + JSON Schema 校验 | - | ✅ |
| T-GEN-02 | 实现 HTML 文本提取器（复用/扩展 `_GDALDocParser`） | - | ✅ |
| T-GEN-03 | 实现 LLM 生成 Prompt + `LLMTemplateGenerator` | T-GEN-01, T-GEN-02 | ✅ |
| T-GEN-04 | 实现 LLM 审核 Prompt + `LLMTemplateReviewer` | T-GEN-01 | ✅ |
| T-GEN-05 | 实现 J2 渲染器 + 安全校验集成 | T-GEN-01 | ✅ |
| T-GEN-06 | 实现状态缓存 + 断点续传机制 | - | ✅ |
| T-GEN-07 | 实现审核队列（JSONL 输出/导入） | T-GEN-04 | ✅ |
| T-GEN-08 | 实现 `generate_templates()` 主流程 + CLI | T-GEN-03~07 | ✅ |
| T-GEN-09 | 编写单元测试 | T-GEN-01~05 | ⬜ |
| T-GEN-10 | 编写集成测试（使用真实 GDAL HTML） | T-GEN-08 | ⬜ |
