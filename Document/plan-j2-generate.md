# plan-j2-generate

| 项目 | 内容 |
|------|------|
| 版本 | v1.0.0 |
| 状态 | 草案 |
| 作者 | - |
| 日期 | 2026-05-29 |

---

## 1. 设计概述

### 1.1 模块职责

实现一个**开发时独立工具**，将 GDAL HTML 文档批量转换为 GIS Agent 可用的 Jinja2 模板（`*.j2`）。该工具不是运行时组件，仅在需要扩充模板库时由开发者执行。

核心流程：HTML 解析 → LLM 生成模板定义 → LLM 审核 → J2 渲染 → 人工终审队列。

### 1.2 所属架构层次

独立工具层（`tools/`），**不属于核心架构的任何一层**。开发时运行，不进入生产运行时。

可复用以下现有模块：
- `rag.preprocess._GDALDocParser` — HTML 结构化提取
- `llm.client.LLMClient` — LLM API 调用（含重试、截断）
- `templates.engine.ScriptSecurityChecker` — 渲染后安全校验
- `templates.scanner.scan_templates` — 生成后验证可扫描性

### 1.3 对应需求项

| 需求 ID | 需求描述 |
|:-------:|---------|
| P1 | 所有 GDAL 命令必须通过 J2 模板渲染，本工具是模板库的批量生产手段 |
| P4 | 模板元数据（`@param`、`@concept` 等）必须完整准确 |
| P5 | 复用现有 anthropic/jinja2 依赖，不引入新生产依赖 |

---

## 2. 设计决策

### DC-0080: 独立开发时工具，不进入运行时

**决策**: 工具代码放置在 `SourceCode/scripts/`（或独立 `tools/` 目录），以 CLI 脚本形式执行，不纳入 `src/` 包结构。

**理由**:
- 该工具的使命是"生产模板"，不是"服务用户请求"
- 运行一次可能消耗大量 LLM token，不适合作为常规功能暴露
- 保持核心代码库的精简，避免开发辅助逻辑污染运行时

**目录定位**:
```
SourceCode/scripts/generate_templates.py    # 主 CLI 入口
SourceCode/scripts/generate/                # 工具内部模块（可选子目录）
```

### DC-0081: 双阶段 LLM 流程（生成 → 审核）

**决策**: 每个 HTML 文件经历两个独立的 LLM 调用：
1. **生成阶段**：LLM 根据提取的 HTML 文本，输出结构化的 `TemplateDefinition`（JSON）
2. **审核阶段**：另一个 LLM 调用（或同一模型不同 prompt）对 `TemplateDefinition` 进行质量检查，输出审核报告

**理由**:
- 生成与审核解耦，便于独立迭代 prompt
- 审核可作为质量门禁，拦截明显错误的模板（如参数类型不匹配、命令语法错误）
- 两阶段均失败时进入人工审核队列，不直接丢弃

**流程图**:
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
| `category` | string | `vector` / `raster` / `general` |
| `command_template` | string | 必须包含 Jinja2 `{{ }}` 变量，且所有参数名均须在模板中出现 |
| `params[].type` | string | 枚举: `file_path`, `crs`, `string`, `boolean`, `integer`, `float` |
| `params[].required` | boolean | 必填参数不允许有 `default` |

### DC-0083: 人工审核队列机制

**决策**: 在任一阶段失败的 HTML 文件不直接丢弃，而是输出到人工审核队列（JSONL 文件），包含失败原因和原始 LLM 输出，供开发者手动修正后重新提交。

**理由**:
- LLM 不是 100% 可靠，某些复杂的 GDAL 命令格式可能无法正确解析
- 人工修正后的案例可用于 few-shot prompt 优化，形成正向循环
- 不丢失任何输入，确保批量处理的可追溯性

**队列文件格式**（JSON Lines）:
```json
{"source_html": "programs/ogr2ogr.html", "stage": "generation", "reason": "无法从 Synopsis 提取命令骨架", "raw_llm_output": "...", "extracted_text": "...", "timestamp": "2026-05-29T10:00:00Z"}
{"source_html": "drivers/gpkg.html", "stage": "review", "reason": "审核发现参数 'layer' 类型推断错误（应为 string 而非 file_path）", "template_def": {...}, "timestamp": "2026-05-29T10:05:00Z"}
```

### DC-0084: 批量处理与断点续传

**决策**: 工具支持批量目录扫描，已处理且通过的 HTML 文件跳过（基于输出文件存在性 + 内容哈希），支持中断后恢复。

**理由**:
- 批量处理可能耗时较长（LLM API 调用有延迟）
- 避免重复消费 token
- 便于增量更新（GDAL 文档更新后只处理变更文件）

**状态跟踪**:
- 在输出目录下生成 `.generate_state.json`，记录已处理的 `(source_path, content_hash, output_path, status)`
- 启动时加载状态文件，跳过 `status == "success"` 且哈希未变的条目

### DC-0085: LLM 生成 Prompt 设计

**决策**: 生成阶段采用 few-shot prompt，提供 2-3 个 GDAL 工具（简单、中等、复杂）的 HTML 提取文本 → TemplateDefinition 示例。

**Prompt 结构**:
```
System: 你是一名 GDAL 命令行专家。根据提供的 HTML 文档提取信息，生成 GIS Agent 使用的 Jinja2 模板定义。

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
[提取的 HTML 文本]
---

输出严格 JSON，不要 markdown 代码块，不要额外解释。
```

### DC-0086: LLM 审核 Prompt 设计

**决策**: 审核阶段采用检查清单（checklist）形式的 prompt，要求 LLM 逐项检查并给出通过/不通过判定。

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

### DC-0087: 审核通过标准

**决策**: 审核结果分级处理：
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

### 3.1 主入口函数

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

### 3.2 返回值

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

## 4. 异常处理

| 异常场景 | 处理策略 |
|---------|---------|
| LLM API 调用失败（网络/限流） | 复用 LLMClient 的指数退避重试（DC-0034），3 次后标记该文件为失败 |
| LLM 输出不符合 JSON Schema | 尝试 markdown JSON 剥离（复用 diagnosis.py 的 `_strip_markdown_json`），仍失败则记录到审核队列 |
| J2 渲染语法错误 | 记录到审核队列，附原始 TemplateDefinition |
| 安全校验发现危险模式 | 记录到审核队列，标记 severity=critical |
| 输出文件已存在 | 默认跳过（基于状态缓存），`--force` 时覆盖 |
| 磁盘写入失败 | 抛出异常，终止程序 |

---

## 5. 测试策略

### 5.1 单元测试

| 测试用例 | 目标 |
|---------|------|
| `test_html_parser_integration` | 验证 `_GDALDocParser` 能正确提取至少 3 种典型 GDAL 工具的 Synopsis + Options |
| `test_template_def_validation` | 验证 JSON Schema 校验能捕获缺失字段、非法类型、命令模板语法错误 |
| `test_review_checklist_scoring` | 验证审核输出解析：全通过、有 warning、有 error 三种情况 |
| `test_state_file_persistence` | 验证断点续传状态文件的正确读写 |
| `test_render_pipeline` | 验证 TemplateDefinition → J2 文本 → scanner 可正确解析的完整链路 |

### 5.2 集成测试

| 测试用例 | 目标 |
|---------|------|
| `test_e2e_ogr2ogr` | 使用真实的 `ogr2ogr.html`，验证端到端生成可工作的 J2 模板 |
| `test_e2e_gdalwarp` | 使用真实的 `gdalwarp.html`，验证复杂参数（坐标变换、裁剪等）的正确提取 |
| `test_dry_run_no_side_effects` | 验证 `--dry-run` 不修改任何文件 |
| `test_review_queue_format` | 验证审核队列 JSONL 可被人工阅读并手动修正后重新导入 |

---

## 6. 复杂度评估

| 维度 | 评级 | 说明 |
|------|------|------|
| 架构复杂度 | 中 | Pipeline 模式，5 个阶段清晰分离，无循环依赖 |
| LLM Prompt 工程难度 | 中高 | Few-shot 示例需要覆盖典型 GDAL 工具格式；Schema 约束需严格 |
| 与现有系统集成 | 低 | 仅 import 现有模块，无接口变更 |
| 审核机制设计 | 中 | Checklist 式审核标准清晰，但 LLM 输出稳定性需迭代优化 |
| 批处理与容错 | 中 | 断点续传、并发控制、失败队列均为常规工程问题 |
| **总体评估** | **中等偏高** | 核心风险在于 LLM 生成质量的不稳定性；工程框架本身不复杂 |

### 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| LLM 对某些 GDAL 工具生成质量差 | 审核队列积压 | 持续积累 few-shot 示例，优化 prompt；人工修正后反哺 |
| LLM API 成本过高 | 批量处理不可持续 | 实现断点续传避免重复；限制 `--max-workers`；支持单文件调试模式 |
| 生成的模板与运行时需求不匹配 | 模板无法使用 | 生成后自动运行 `scan_templates()` 验证可解析性；集成测试覆盖 |

---

## 7. 实现任务拆分

| 任务 ID | 内容 | 依赖 |
|---------|------|------|
| T-GEN-01 | 实现 `TemplateDefinition` dataclass + JSON Schema 校验 | - |
| T-GEN-02 | 实现 HTML 文本提取器（复用/扩展 `_GDALDocParser`） | - |
| T-GEN-03 | 实现 LLM 生成 Prompt + `LLMTemplateGenerator` | T-GEN-01, T-GEN-02 |
| T-GEN-04 | 实现 LLM 审核 Prompt + `LLMTemplateReviewer` | T-GEN-01 |
| T-GEN-05 | 实现 J2 渲染器 + 安全校验集成 | T-GEN-01 |
| T-GEN-06 | 实现状态缓存 + 断点续传机制 | - |
| T-GEN-07 | 实现审核队列（JSONL 输出/导入） | T-GEN-04 |
| T-GEN-08 | 实现 `generate_templates()` 主流程 + CLI | T-GEN-03~07 |
| T-GEN-09 | 编写单元测试 | T-GEN-01~05 |
| T-GEN-10 | 编写集成测试（使用真实 GDAL HTML） | T-GEN-08 |
