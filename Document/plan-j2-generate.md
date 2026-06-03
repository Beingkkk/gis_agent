# plan-j2-generate

| 项目 | 内容 |
|------|------|
| 版本 | v3.2.0 |
| 状态 | 在线模式 v3.2.0 已实现，CLI 集成测试待补充 |
| 作者 | - |
| 日期 | 2026-06-03 |

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

### DC-0088: 文档提取器——文件导入与噪音过滤

**决策**: 在线模式支持通过文件上传导入 HTML/Markdown 文档。后端提供独立的 `HtmlExtractor` 和 `MarkdownExtractor`，在 LLM 生成前清理文档噪音（导航栏、脚本、样式、YAML frontmatter 等），减少 token 消耗并提升生成质量。

**理由**:
- 原始 HTML 文档含有大量导航、脚本、样式等 LLM 无关内容，直接输入浪费 token 且干扰生成质量
- Markdown 文档常包含 YAML frontmatter、链接语法等格式化噪音，需要预处理
- 提取与 LLM 生成解耦：用户可在导入后预览清洗结果，不满意可手动编辑后再生成
- 复用标准库实现，零额外依赖（`html.parser.HTMLParser`）

**支持的文件格式**:
| 格式 | 扩展名 | 清洗策略 |
|------|--------|---------|
| HTML | `.html`, `.htm` | 移除 `script/style/nav/footer/header/aside` 等噪音标签，提取正文文本 |
| Markdown | `.md`, `.markdown` | 移除 YAML frontmatter，转换链接为纯文本，清理粗体/斜体标记 |

**在线模式导入流程**:
```
用户选择文件 (.html/.md)
    │
    ▼
前端 FileReader 读取原始内容
    │
    ▼
POST /generator/parse-document {content, file_type}
    │
    ▼
HtmlExtractor / MarkdownExtractor 清洗
    │
    ▼
返回清洗后文本 → 前端填入输入框
    │
    ▼
用户确认/编辑后 → 进入 Step 2 生成
```

**代码位置**:
- `templates/extractors.py` — `HtmlExtractor`（基于 `HTMLParser`） + `MarkdownExtractor`
- `api/routes/generator.py` — `POST /generator/parse-document`
- `frontend/src/pages/GeneratorPage.tsx` — Step 1 文件导入 UI

### DC-0094: 统一模板生成引擎

**决策**: 将 CLI 批量模式 (`scripts/generate/generator.py`) 的完整生成引擎（系统提示词、few-shot 示例、鲁棒 JSON 解析、参数补全、重试逻辑）提取到 `src/llm/template_generator.py`，使在线交互模式和 CLI 批量模式共用同一套生成逻辑。

**理由**:
- 当前在线模式使用简化提示词（20 行）+ 3 策略 JSON 解析，生成质量明显弱于 CLI 的完整引擎
- DC-0090 已声明两种模式底层逻辑统一，但当前实现存在漂移
- 提取为共享模块后，prompt 优化和解析策略改进只需修改一处

**共享逻辑清单**（提取后）:
| 逻辑 | 在线模式调用 | CLI 批量模式调用 |
|------|------------|-----------------|
| 系统提示词 + few-shot | `template_generator.SYSTEM_PROMPT` | `template_generator.SYSTEM_PROMPT` |
| JSON 解析（含 bare key 修复） | `template_generator.parse_generated_response()` | `template_generator.parse_generated_response()` |
| 参数补全（未声明变量→boolean） | `template_generator.auto_complete_params()` | `template_generator.auto_complete_params()` |
| 参数清洗（required+default 冲突） | `template_generator.sanitize_params()` | `template_generator.sanitize_params()` |
| 同步生成（含重试） | `template_generator.generate_template_sync()` | `template_generator.generate_template_sync()` |
| 流式生成 | `template_generator.generate_template_stream()` | — |
| **.j2 组装（JSON → 完整模板文件）** | `template_generator.assemble_j2_body()` | `renderer.py::render_j2()` |

**返回格式**: 共享引擎返回 `dict[str, Any]`（解析后的 LLM JSON），由调用方转换为各自的输出格式（API → `GeneratedTemplateResponse`，CLI → `TemplateDefinition`）。

**API 层组装**: 在线模式的 `POST /generator/generate` 和 `WS /ws/generator/generate` 在收到 LLM 返回的 JSON 后，调用 `assemble_j2_body()` 将结构化数据组装为完整 `.j2` 文件内容（含 `{# @id/@name/@param... #}` comment header + `@echo off` + 命令体 + `REM Done`），与 CLI 的 `renderer.py::render_j2()` 输出格式一致。这样前端预览和保存的始终是可直接放入 `data/templates/` 的标准 `.j2` 文件。

### DC-0095: 多文件导入与 Token 预算检查

**决策**: `POST /generator/parse-document` 支持多文件数组输入。合并清洗后的文本，计算预估 token 数。**Token 预算检查只在调用 LLM 前执行**（`POST /generator/generate` 和 `WS /ws/generator/generate`），`parse-document` 本身不拦截，用户可自由导入文件并预览清洗结果。

**理由**:
- GDAL 文档常分散在多个 HTML 页面中，单文件导入限制用户体验
- `LLMClient._truncate_messages()` 会在后台静默截断超长输入，导致关键参数信息丢失、生成质量下降
- 清洗结果预览是用户决策的一部分，不应因 token 数而阻断导入流程
- 拦截点后置到 LLM 调用前，符合"提取后、输入 LLM 前判断"的直觉

**Token 预算**:
- 预估公式: `total_cleaned_chars // 4`（与 `LLMClient._estimate_tokens` 相同启发式）
- 预算上限: **12000 tokens**（Claude 200K 上下文，预留约 12000 给用户文档 + ~1500 给 system prompt / few-shot examples）
- 检查位置:
  - `POST /generator/generate` → HTTP 413
  - `WS /ws/generator/generate` → error frame（stage=validation）
  - `parse-document` → **不检查**，始终返回 200

**前端 UX**:
- Step 1 显示预估 token 数和 `12000` 上限参考
- 超预算时显示**黄色警告**（不阻止"下一步"），提示"文档较长，生成可能需要更长时间"
- Step 2 "生成模板"按钮不因 token 数禁用，由后端在调用 LLM 时统一拦截

**合并策略**: 多份清洗后文本按文件顺序拼接，用 `---\n` 分隔。

### DC-0096: WebSocket 流式模板生成

**决策**: 新增 WebSocket 端点 `/ws/generator/generate`（无 `session_id`，模板生成器独立于 Session 状态机）。前端通过 WebSocket 接收 LLM 生成的实时 chunk，消除 HTTP 30s 超时问题。

**理由**:
- LLM 模板生成本身需要 20-60s，HTTP 30s 超时频繁触发
- CODE-5 要求流式交互必须使用 WebSocket
- 实时显示生成过程提升用户信任度（"正在分析文档..." → 逐步看到 JSON 结构输出）

**协议**:
- Client → Server: `{"type": "start", "document_text": "...", "config": {"category": "...", "tool_source": "..."}}`
- Server → Client (streaming): `{"type": "chunk", "content": "..."}`
- Server → Client (complete): `{"type": "done", "result": {"template_id": "...", ...}}`
- Server → Client (error): `{"type": "error", "message": "...", "stage": "generation|parsing|validation"}`

**前端集成**: Step 2 点击"生成模板"后建立 WebSocket 连接，显示流式面板（实时文本预览 + 取消按钮）。生成完成后自动进入 Step 3。

**HTTP Fallback**: `POST /generator/generate` 保留为同步备用，内部调用 `generate_template_sync()`。

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

#### `POST /api/generator/parse-document`

将原始 HTML/Markdown 文档清洗为 LLM 可用的纯文本。支持单文件或多文件。

**Request** (多文件):
```json
{
  "files": [
    {"content": "<!DOCTYPE html><html>...</html>", "file_type": "html"},
    {"content": "# gdalwarp\n...", "file_type": "markdown"}
  ]
}
```

**Response**:
```json
{
  "files": [
    {"file_type": "html", "raw_chars": 15000, "cleaned_chars": 3200},
    {"file_type": "markdown", "raw_chars": 8000, "cleaned_chars": 2100}
  ],
  "document_text": "... merged text with --- separators ...",
  "total_raw_chars": 23000,
  "total_cleaned_chars": 5300,
  "estimated_tokens": 1325
}
```

**错误处理**:
- `400` — `files` 为空数组或包含不支持的 `file_type`
- `parse-document` 本身**不检查** token 预算，始终返回 200（含 `estimated_tokens` 供前端参考）

**设计**: DC-0088, DC-0095

#### `WS /ws/generator/generate`

流式模板生成 WebSocket（无 `session_id`，模板生成器独立于 Session 状态机）。

**连接**: `ws://<host>:<port>/ws/generator/generate`

**Client → Server** (连接建立后发送):
```json
{"type": "start", "document_text": "...", "config": {"category": "vector", "tool_source": "GDAL"}}
```

**Server → Client** (流式输出):
```json
{"type": "chunk", "content": "..."}
```

**Server → Client** (生成完成，返回结构化结果):
```json
{
  "type": "done",
  "result": {
    "template_id": "ogr2ogr_convert",
    "name": "矢量格式转换",
    "description": "...",
    "body": "{# @id ogr2ogr_convert #}\n...",
    "params": [{"name": "input", "type": "file_path", "required": true}],
    "concepts": ["..."],
    "notes": ["..."]
  }
}
```

**Server → Client** (错误):
```json
{"type": "error", "message": "...", "stage": "generation|parsing|validation"}
```

**错误场景**:
| stage | 触发条件 |
|-------|---------|
| `validation` | document_text 为空 / token 预算超限 / 协议消息格式错误 |
| `generation` | LLM API 调用失败（网络/认证/限流） |
| `parsing` | LLM 输出不符合 JSON 格式，解析失败 |

**设计**: DC-0096

---

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
│  [←] GIS Agent    J2 模板生成器                    ─ □ ✕    │
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

**左上角返回按钮**（DC-UX-07a）：`TopBar` 组件支持 `backTo` prop，当传入 `"/"` 时在左上角 Logo 旁显示返回箭头，点击路由回主应用。

### 4.2 五步向导

| 步骤 | 标题 | 内容 | 操作 |
|------|------|------|------|
| **1** | 输入文档 | 粘贴文本 **或** 导入多个文件（.html/.md），文件经后端解析器清洗后填入文本框，显示每文件原始→清洗字符数统计 + 总预估 token 数。token 超限时显示黄色警告（不阻止流程） | 下一步 |
| **2** | 配置属性 | 分类选择（vector/raster/general/database）、工具来源输入。点击"生成模板"后建立 WebSocket 连接，显示流式生成面板（实时文本预览 + 取消按钮） | 上一步 / 生成模板 / 取消 |
| **3** | 预览结果 | 展示生成的模板元数据（ID、名称、参数列表）+ 模板体代码预览 | 上一步 / 编辑模板 / 安全审查 |
| **4** | 审查结果 | 安全校验结果展示（通过/失败 + 错误列表）。通过时显示保存按钮 | 上一步 / 保存模板 |
| **5** | 保存成功 | 成功提示、保存路径、返回主应用 / 再生成一个 | - |

### 4.3 Step 1 多文件导入 UI

Step 1 文件导入区域支持多文件选择：

```
┌──────────────────────────────────────────────────────────────┐
│  [选择文件]  支持 .html、.md 格式，自动提取正文并去除噪音      │
├──────────────────────────────────────────────────────────────┤
│  📄 ogr2ogr.html      HTML      15,000 → 3,200 字符    [×]  │
│  📄 gdalwarp.md       Markdown   8,000 → 2,100 字符    [×]  │
├──────────────────────────────────────────────────────────────┤
│  总计: 23,000 → 5,300 字符  预估 token: 1,325                │
└──────────────────────────────────────────────────────────────┘
```

- `<input type="file" multiple accept=".html,.htm,.md,.markdown">`
- 每文件显示：文件名、类型标签、原始字符数、清洗后字符数、删除按钮
- 底部显示总计和预估 token（`total_cleaned_chars // 4`）
- `estimated_tokens > 12000` 时：黄色警告横幅（"文档较长，生成可能需要更长时间"），不阻止"下一步"
- 删除单个文件后重新计算总计
- Step 2 "生成模板"按钮不因 token 数禁用

### 4.4 Step 2 流式生成面板

点击"生成模板"后，配置表单下方展开流式面板：

```
┌──────────────────────────────────────────────────────────────┐
│  ⚙️ 正在生成模板...                                    [取消] │
├──────────────────────────────────────────────────────────────┤
│  {                                                           │
│    "template_id": "ogr2ogr_convert",                         │
│    "name": "矢量格式转换",                                    │
│    ...                                                       │
│  }                                                           │
└──────────────────────────────────────────────────────────────┘
```

- 面板内实时显示累积的 LLM 输出（等宽字体，自动滚动到底部）
- "取消"按钮调用 `ws.close()`，终止生成
- 生成完成后面板自动收起，进入 Step 3
- 生成失败时面板显示错误信息，保留"重试"按钮

**WebSocket 连接流程**:
1. 构建 URL：`ws://` + `getApiBaseUrl().replace('http://', '')` + `/ws/generator/generate`
2. `new WebSocket(url)` → `onopen` → `send({type: "start", document_text, config})`
3. 接收 `chunk` → 追加到 `streamedText` → 面板实时更新
4. 接收 `done` → `setGenerated(result)` → `setStep(3)` → `ws.close()`
5. 接收 `error` → `setErrorMsg(message)` → `ws.close()`

### 4.5 Step 3 编辑器交互

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
| 文档超出 token 预算 | Step 1 黄色警告（不阻止"下一步"）；后端 `parse-document` 返回 `estimated_tokens`；`POST /generator/generate` 返回 413；WebSocket 返回 `{"type": "error", "stage": "validation"}` |
| LLM API 调用失败 | WebSocket 发送 `{"type": "error", "stage": "generation"}`；前端展示错误提示，保留用户输入，允许重试 |
| LLM 输出不符合 JSON | WebSocket 发送 `{"type": "error", "stage": "parsing"}`；前端展示"生成失败，请检查输入文档是否包含足够的命令信息" |
| J2 渲染语法错误 | 前端 Step 4 展示错误详情，提供"返回编辑"按钮 |
| 安全校验发现危险模式 | `ScriptSecurityChecker` 对模板文件内容（含 Jinja2 语法）做检查：Jinja2 filter `{{ var \| quote }}` 中的 `\|` 不是 shell 管道，需跳过；真正的 shell 管道/分隔符（`\|`, `;`, `&&` 等）仍被拦截。前端 Step 4 红色提示，列出具体问题，禁止保存 |
| 模板 ID 已存在 | `409` 响应，前端提示"模板已存在，是否覆盖？"，用户确认后带 `overwrite=true` 重试 |
| WebSocket 连接失败 | 前端显示"连接失败，请重试"，提供回退到 HTTP 生成按钮 |
| 用户取消生成 | 前端 `ws.close()`，后端停止 chunk 发送；前端恢复"生成模板"按钮 |

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
| `test_generator_api_generate` | 验证 `/generator/generate` 能正确调用共享引擎并返回结构化数据 |
| `test_generator_api_generate_token_budget` | 验证 document_text 超过 12000 tokens 时返回 413 |
| `test_generator_api_validate_pass` | 验证有效模板通过安全校验和语法校验 |
| `test_generator_api_validate_fail_security` | 验证包含危险模式的模板返回 `valid=false` |
| `test_generator_api_save_success` | 验证保存后文件存在且触发注册表重扫描 |
| `test_generator_api_save_conflict` | 验证重复保存返回 `409`，覆盖后成功 |
| `test_generator_api_save_categorized` | 验证模板按 category 保存到子目录 |
| `test_generator_api_parse_html` | 验证 HTML 文档清洗：移除 script/nav/footer，保留正文 |
| `test_generator_api_parse_markdown` | 验证 Markdown 清洗：移除 frontmatter，转换链接为纯文本 |
| `test_generator_api_parse_multi_file` | 验证多文件合并清洗，含预估 token 数 |
| `test_generator_api_parse_large_document` | 验证 `parse-document` 不拦截大文件，始终返回 200（含 estimated_tokens） |
| `test_generator_api_parse_invalid_type` | 验证不支持的 file_type 返回 400 |
| `test_websocket_generator_connect` | 验证 WebSocket 连接建立和 start 消息接收 |
| `test_websocket_generator_stream_chunks` | 验证 chunk 帧按序到达 |
| `test_websocket_generator_done_with_result` | 验证 done 帧包含完整解析结果 |
| `test_websocket_generator_error_token_budget` | 验证超长文档（>12000 tokens）返回 error 帧（stage=validation） |
| `test_websocket_generator_error_parse_fail` | 验证 LLM 输出非 JSON 时返回 error 帧（stage=parsing） |
| `test_llm_template_generator_parse_fences` | 验证 markdown ```json 代码块剥离 |
| `test_llm_template_generator_parse_bare_keys` | 验证未加引号的 JSON key 自动修复 |
| `test_llm_template_generator_sanitize_required_default` | 验证 required=true + default → required=false |
| `test_llm_template_generator_sanitize_enum_no_options` | 验证空 enum options → 占位符 |
| `test_llm_template_generator_auto_complete_vars` | 验证模板体中未声明变量自动补全为 boolean |
| `test_llm_template_generator_sync_retry` | 验证首次解析失败后自动重试（temp 0.1→0.2） |
| `test_llm_template_generator_stream_chunks` | 验证 streaming 模式下 on_chunk 接收完整文本 |
| `test_html_extractor_noise_removal` | 验证 HtmlExtractor 跳过噪音标签（script/style/nav/footer） |
| `test_html_extractor_block_tags` | 验证块级标签引入换行 |
| `test_markdown_extractor_frontmatter` | 验证 YAML frontmatter 移除 |
| `test_markdown_extractor_links` | 验证 `[text](url)` → `text` |

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
| T-GEN-WEB-05 | 前端模板体编辑器（编辑模式 + 重新校验） | T-GEN-WEB-04 | ✅ |
| T-GEN-WEB-06 | 导航栏集成 GeneratorPage 入口 | - | ✅ |
| T-GEN-WEB-07 | 保存成功后注册表热加载 + 前端提示 | T-GEN-WEB-03 | ✅ |
| T-GEN-WEB-08 | 文档提取器：HtmlExtractor + MarkdownExtractor（标准库实现） | - | ✅ |
| T-GEN-WEB-09 | 文件导入 UI：Step 1 支持 .html/.md 导入 + 清洗结果预览 | T-GEN-WEB-08 | ✅ |
| T-GEN-WEB-10 | TopBar 返回按钮（backTo prop，GeneratorPage 传入 "/"） | DC-UX-07a | ✅ |
| T-GEN-WEB-11 | 统一生成引擎：提取 CLI 的完整引擎到 `src/llm/template_generator.py` | DC-0094 | ✅ |
| T-GEN-WEB-12 | API 路由改用共享引擎：`POST /generator/generate` 调用 `generate_template_sync()` | T-GEN-WEB-11 | ✅ |
| T-GEN-WEB-13 | 多文件导入：`POST /generator/parse-document` 支持文件数组 + token 预算检查（后置到 generate） | DC-0095 | ✅ |
| T-GEN-WEB-14 | 前端多文件 UI：Step 1 文件列表 + token 统计 + 超限黄色警告（不阻止下一步） | T-GEN-WEB-13 | ✅ |
| T-GEN-WEB-15 | WebSocket 流式生成：`/ws/generator/generate` 端点 + 前端流式面板 | DC-0096 | ✅ |
| T-GEN-WEB-16 | CLI 批量模式适配：导入共享引擎，保持向后兼容 | T-GEN-WEB-11 | ✅ |

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
| T-GEN-09 | 编写单元测试 | T-GEN-01~05 | ✅ |
| T-GEN-10 | 编写集成测试（使用真实 GDAL HTML） | T-GEN-08 | ⬜ |

---

## 附录：变更记录

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v3.2.0 | 2026-06-03 | **完整 .j2 组装**（DC-0094 v2）：API/WS 返回的 `body` 由裸 `command_template` 改为调用 `assemble_j2_body()` 组装的标准 `.j2` 文件（含 comment header + `@echo off` + 命令体），与 CLI `renderer.py` 输出格式一致；**安全校验 Jinja2 感知**：`ScriptSecurityChecker.check()` 在检测到模板文件时先清理 Jinja2 构造（`{{...}}`、`{#...#}`、`{%...%}`），避免 `\|` filter 被误判为 shell 管道；前端预览 `pre` 默认文字颜色改为 `text-gray-300` 解决黑色背景看不清问题 |
| v3.1.0 | 2026-06-03 | **Token 预算策略调整**（DC-0095 v2）：预算上限从 2000 提升到 12000 tokens；检查位置从 `parse-document` 前移到 `generate` / WebSocket 调用前；`parse-document` 不再拦截，始终返回 200 含 `estimated_tokens`；前端 Step 1 超预算时改为黄色警告（不阻止"下一步"），Step 2 "生成模板"按钮不因 token 数禁用；测试用例同步更新；T-GEN-WEB-11~16 标记为已完成 |
| v3.0.0 | 2026-06-03 | **统一生成引擎**（DC-0094）：提取 CLI 完整引擎到 `src/llm/template_generator.py`，在线模式与批量模式共用提示词/解析/重试/参数补全逻辑；**多文件导入**（DC-0095）：`parse-document` 支持文件数组，前端显示 token 预算检查，超限时明确提示；**WebSocket 流式生成**（DC-0096）：新增 `/ws/generator/generate` 端点，前端 Step 2 显示实时流式面板，消除 HTTP 30s 超时；新增 T-GEN-WEB-11~16；测试策略补充共享引擎、WebSocket、多文件用例 |
| v2.1.0 | 2026-06-03 | 同步实现状态：T-GEN-WEB-05（前端编辑器）、T-GEN-WEB-07（热加载提示）、T-GEN-09（单元测试）标记为已实现；版本状态更新为"在线模式已实现" |
| v2.0.0 | 2026-05-30 | 初版，定义双模式模板生成器架构 |
