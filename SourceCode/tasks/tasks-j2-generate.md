# J2 模板自动生成任务清单

> 基于 `plan-j2-generate.md` (DC-0080 ~ DC-0087)
> 创建日期: 2026-05-29

---

## 模块总览

实现 GDAL HTML 文档 → Jinja2 模板的批量自动生成工具。

| 组件 | 文件 | 职责 |
|------|------|------|
| `TemplateDefinition` | `scripts/generate/models.py` | LLM 输出 JSON 的结构化 dataclass + Schema 校验 |
| `HtmlExtractor` | `scripts/generate/extractor.py` | HTML 文本提取（复用/扩展 `_GDALDocParser`） |
| `LLMTemplateGenerator` | `scripts/generate/generator.py` | 调用 LLM 生成 TemplateDefinition |
| `LLMTemplateReviewer` | `scripts/generate/reviewer.py` | 调用 LLM 审核模板质量 |
| `J2Renderer` | `scripts/generate/renderer.py` | TemplateDefinition → .j2 文件渲染 |
| `generate_templates()` | `scripts/generate_templates.py` | CLI 主入口 + 批量协调 |

**依赖关系**:
```
generate_templates() → HtmlExtractor → LLMTemplateGenerator → LLMTemplateReviewer → J2Renderer
                     ↘ LLMClient (复用 llm/client.py)
```

---

## PoC 阶段：单文件端到端验证 (ogr2ogr.html)

**目标**: 跑通 `ogr2ogr.html` → `.j2` 的完整链路，验证 LLM 输出质量。

### T-GEN-PoC-01: 实现最小可运行提取 + LLM 生成脚本

**设计依据**: plan-j2-generate §3.1, DC-0081, DC-0085

- [ ] `scripts/poc_generate.py`: 单文件 PoC 脚本
  - 复用 `rag.preprocess.extract_text_from_html()` 提取文本
  - 构建 few-shot prompt（含 shp2geojson/reproject 作为示例）
  - 调用 `LLMClient.chat()` 生成 TemplateDefinition JSON
  - 解析 JSON，基础校验（必填字段、参数名在命令模板中出现）
  - 渲染为 .j2 文件

**验收标准**:
- PoC 脚本不修改任何 `src/` 包代码
- 能从 `ogr2ogr.html` 提取 Synopsis + Description + 前 20 个 Options
- LLM 输出可解析为有效的 JSON
- 生成的 .j2 文件可被 `scan_templates()` 正确解析

### T-GEN-PoC-02: 评估 LLM 输出质量

**设计依据**: plan-j2-generate §6, DC-0085

- [ ] 人工检查 LLM 生成的 `TemplateDefinition`，评估：
  - `id` 是否符合 `[a-z0-9_]+`
  - `command_template` 是否为有效的 Jinja2 语法
  - 参数类型推断是否合理（file_path / crs / string / boolean）
  - `| quote` 过滤是否正确应用于路径/字符串参数
  - `@concept` / `@note` / `@common_error` 是否准确（非臆造）
- [ ] 记录问题清单，用于优化 prompt

**验收标准**:
- 至少 80% 的参数类型推断正确
- 命令模板语法 100% 正确
- 概念/说明文本与文档描述一致

---

## 正式实现阶段

### T-GEN-01: TemplateDefinition 数据模型 + Schema 校验

**设计依据**: plan-j2-generate §3.2, DC-0082

**红 — 编写测试**:
- [ ] `tests/unit/test_generate_models.py`:
  - `test_template_def_required_fields`: 缺少 `id`/`name`/`command_template` 时抛出 ValidationError
  - `test_param_type_enum`: 仅允许 `file_path`, `crs`, `string`, `boolean`, `integer`, `float`
  - `test_param_names_in_template`: 参数名未在 `command_template` 中出现时抛出 ValidationError
  - `test_required_no_default`: `required=True` 时不能有 `default`
  - `test_id_format`: `id` 不符合 `[a-z0-9_]+` 时抛出 ValidationError

**绿 — 实现代码**:
- [ ] `scripts/generate/models.py`: `TemplateDefinition` + `ParamDef` dataclass
- [ ] `@dataclass` + `__post_init__` 校验，不依赖外部库（P5）

---

### T-GEN-02: HTML 文本提取器

**设计依据**: plan-j2-generate §2, DC-0080

**红 — 编写测试**:
- [ ] `tests/unit/test_generate_extractor.py`:
  - `test_extract_synopsis`: 能从 `ogr2ogr.html` 提取 Synopsis 区块
  - `test_extract_description`: 能提取 Description 前 3 段
  - `test_extract_options`: 能提取前 N 个 option 的 name + description
  - `test_extract_concepts`: 能从文档中提取核心概念文本

**绿 — 实现代码**:
- [ ] `scripts/generate/extractor.py`: `extract_for_generation(html, max_options=20)`
  - 复用 `_GDALDocParser` 提取基础结构
  - 额外提取：Synopsis 原始文本、Description 摘要、Option 列表

---

### T-GEN-03: LLM 模板生成器

**设计依据**: plan-j2-generate §2.5, DC-0085

**红 — 编写测试**:
- [ ] `tests/unit/test_generate_generator.py`:
  - `test_prompt_contains_few_shot`: prompt 中包含示例
  - `test_prompt_contains_rules`: prompt 中包含规则说明
  - `test_parse_valid_json`: 能解析 LLM 返回的合法 JSON
  - `test_parse_markdown_json`: 能剥离 markdown 代码块后解析 JSON
  - `test_invalid_json_fallback`: JSON 解析失败时返回 None + reason

**绿 — 实现代码**:
- [ ] `scripts/generate/generator.py`: `LLMTemplateGenerator`
  - `generate(extracted_text) -> TemplateDefinition | None`
  - 内联 few-shot prompt 常量
  - markdown JSON 剥离（复用 `diagnosis.py` 逻辑）

---

### T-GEN-04: LLM 模板审核器

**设计依据**: plan-j2-generate §2.6, DC-0086, DC-0087

**红 — 编写测试**:
- [ ] `tests/unit/test_generate_reviewer.py`:
  - `test_review_pass`: 合法 TemplateDefinition → passed=True, issues=[]
  - `test_review_param_type_error`: `t_srs` 类型为 `string` 而非 `crs` → error
  - `test_review_missing_quote`: 路径参数未用 `| quote` → warning/error
  - `test_review_unknown_param_in_template`: 命令模板含未声明变量 → error

**绿 — 实现代码**:
- [ ] `scripts/generate/reviewer.py`: `LLMTemplateReviewer`
  - `review(template_def) -> ReviewResult`
  - 内联 checklist prompt 常量

---

### T-GEN-05: J2 渲染器

**设计依据**: plan-j2-generate §3.2, DC-0082

**红 — 编写测试**:
- [ ] `tests/unit/test_generate_renderer.py`:
  - `test_render_header`: 正确渲染 `{# @id ... #}` 注释头
  - `test_render_params`: 正确渲染 `{# @param ... #}` 行
  - `test_render_command_template`: 正确渲染命令体
  - `test_render_scanable`: 输出可被 `scan_templates()` 解析

**绿 — 实现代码**:
- [ ] `scripts/generate/renderer.py`: `J2Renderer`
  - `render(template_def) -> str`
  - 生成标准 J2 注释头 + 命令体

---

### T-GEN-06: 状态缓存 + 断点续传

**设计依据**: plan-j2-generate §2.4, DC-0084

**红 — 编写测试**:
- [ ] `tests/unit/test_generate_state.py`:
  - `test_state_load_save`: 状态文件可正确读写
  - `test_skip_processed`: 已处理文件被跳过
  - `test_force_reprocess`: `--force` 时重新处理

**绿 — 实现代码**:
- [ ] `scripts/generate/state.py`: `GenerationState`

---

### T-GEN-07: 审核队列（JSONL 输出/导入）

**设计依据**: plan-j2-generate §2.3, DC-0083

**红 — 编写测试**:
- [ ] `tests/unit/test_generate_queue.py`:
  - `test_queue_append`: 失败记录正确追加到 JSONL
  - `test_queue_readable`: 输出格式人工可读

**绿 — 实现代码**:
- [ ] `scripts/generate/queue.py`: `ReviewQueue`

---

### T-GEN-08: CLI 主入口

**设计依据**: plan-j2-generate §3.3, DC-0080

**红 — 编写测试**:
- [ ] `tests/unit/test_generate_cli.py`:
  - `test_cli_dry_run`: `--dry-run` 不写入文件
  - `test_cli_args_parsing`: 参数正确解析

**绿 — 实现代码**:
- [ ] `scripts/generate_templates.py`: CLI 入口
  - argparse 参数：`--source`, `--output`, `--config`, `--strict`, `--dry-run`, `--force`
  - 协调整个 pipeline

---

## 集成测试

### T-GEN-09: 端到端集成测试

- [ ] `tests/integration/test_generate_e2e.py`:
  - `test_e2e_ogr2ogr`: 使用真实 `ogr2ogr.html`，验证完整 pipeline
  - `test_e2e_gdalinfo`: 使用 `ogrinfo.html`，验证不同工具格式
  - `test_batch_processing`: 批量处理 3 个 HTML 文件

---

## 任务依赖图

```
T-GEN-PoC-01 ──→ T-GEN-PoC-02 ──→ (prompt 优化迭代)
                        │
                        ▼
T-GEN-01 (models) ──────┬──→ T-GEN-03 (generator)
                        │         │
T-GEN-02 (extractor) ───┤         ▼
                        │    T-GEN-04 (reviewer)
                        │         │
                        └──→ T-GEN-05 (renderer)
                                  │
T-GEN-06 (state) ────────────────┤
                                  │
T-GEN-07 (queue) ────────────────┤
                                  ▼
                           T-GEN-08 (CLI)
                                  │
                                  ▼
                           T-GEN-09 (integration)
```
