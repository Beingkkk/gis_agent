# plan-integration

| 项目 | 内容 |
|------|------|
| 版本 | v1.1.0 |
| 状态 | 设计基线 |
| 日期 | 2026-05-28 |
| 前置条件 | plan-core v1.0.0, plan-cli v1.0.0, plan-templates v1.0.0, plan-llm v1.0.0 全部已实现 |

---

## 1. 设计概述

### 1.1 目标

全部底层模块（config/llm/core/templates/cli）已实现并通过单元测试，但各模块之间的**衔接处**尚未经过系统性验证。本次集成工作的目标是：

1. 建立集成测试基建设施，覆盖跨模块的关键衔接点
2. 补充模板数量，使常见 GIS 操作的覆盖率达到可用水平
3. 编写端到端验收测试，从用户视角验证完整对话流
4. 修复启动体验和文档中的不一致问题

### 1.2 范围边界

| 在范围内 | 不在范围内 |
|---------|-----------|
| 集成测试目录搭建 + 测试编写 | 新增外部依赖 |
| 补充 `.j2` 模板文件（不修改已有模板） | 修改已有模块的公共 API |
| README 启动指令修正 | GUI 界面 |
| 端到端 dry-run 验收 | LLM 模型切换 |

---

## 2. 现状诊断

### 2.1 已验证通畅的链路

```
[初始化链]
parse_args → load_config → initialize(workspace)
→ scan_templates → TemplateRegistry → ParamValidator → TemplateEngine
→ LLMClient → PromptBuilder → SessionProcessor → ScriptExecutor → REPL

[状态机链路]
IDLE ──classify_intent──→ PARAM_COLLECT ──extract_params──→ SCRIPT_PREVIEW
  │                          │ ↑                            │
  ├──_find_matching_templates──→ 匹配模板元数据
  ├──answer_question──→ 回答
  └──状态保持 IDLE         └──追问缺失参数─────────────────┘

[执行链路]
SCRIPT_PREVIEW ──render_fn──→ RenderedScript ──subprocess──→ ExecutionResult
```

### 2.2 发现的缺口

| 编号 | 问题描述 | 影响 | 修复策略 |
|:----:|---------|------|---------|
| I1 | 仅 3 个模板（shp2geojson, clip_raster, info_query） | 用户常见操作匹配率极低 | 补充至 8-10 个 |
| I2 | 零集成测试，21 个测试全为单元测试 | 模块衔接问题无法发现 | 创建 `tests/integration/` |
| I3 | 无端到端验收测试 | 无法从用户角度验证可用性 | 编写 e2e 场景测试 |
| I4 | README 启动指令与实际路径不一致 | 用户无法按文档启动 | 修正 README |
| I5 | 模板引擎 `render()` 的 `platform=None` 分支未在集成中验证 | 跨平台渲染可能出错 | 集成测试中覆盖 |
| I6 | Q&A 基于模板元数据，需验证匹配逻辑 | 问答体验 | 集成测试中覆盖模板匹配 + answer_question 链路 |

---

## 3. 设计决策

### DC-0070: 集成测试目录独立于单元测试

**决策**: 集成测试放在 `tests/integration/` 目录，与 `tests/unit/` 分离。

**理由**:
- 集成测试运行慢（涉及模板文件 I/O、LLM mock 组装），与快速的单元测试分离便于单独运行
- 集成测试依赖项目目录结构（模板文件、config.json），不适合并行化
- pytest 支持通过目录过滤：`pytest tests/unit/` vs `pytest tests/integration/`

### DC-0071: 集成测试使用真实模板文件 + mock LLM

**决策**: 集成测试不调用真实 LLM API，但对模板引擎使用真实 `.j2` 文件和 Jinja2 渲染。

**理由**:
- LLM API 调用不稳定、有成本、有延迟，不适合 CI 中的集成测试
- 模板渲染是确定性的，使用真实文件能发现模板语法错误和路径问题
- mock LLM 的返回值足以驱动完整的状态机流转

**mock 策略**:
- `LLMClient.chat()` → 返回预设的 JSON 字符串
- `TemplateEngine` → 使用真实的 `.j2` 文件

### DC-0072: 补充模板遵循已有注释头规范

**决策**: 新增模板沿用 `scanner.py` 解析的 Jinja2 注释头格式（`{# @id ... #}`、`{# @param ... #}`），不引入新元数据格式。

**理由**:
- 已有扫描器已能解析该格式，无需修改代码
- 新增模板只需创建单个 `.j2` 文件，零代码改动

### DC-0073: 验收测试以 dry-run 模式为主

**决策**: 端到端验收测试在 `--dry-run` 模式下运行，不实际执行 GDAL 命令。

**理由**:
- 验收关注的是"从用户输入到脚本生成"的完整链路，而非 GDAL 执行本身
- 避免依赖真实数据文件和 GDAL 环境
- dry-run 模式已能验证脚本内容是否正确渲染

### DC-0074: Q&A 采用模板元数据匹配

**决策**: 文档问答流程基于模板元数据进行匹配，不再依赖向量检索。用户问题先由 `_find_matching_templates()` 通过关键词匹配模板 id、name、description 和 `@concept` 元数据，提取 Top-N 候选模板的元数据作为上下文，传入 `answer_question()` 生成回答。

**理由**:
- RAG 向量检索已移除（ADR-0001），知识源唯一来源为模板元数据
- 模板元数据（`@concept`、`@note`、`@common_error`）经过人工验证，准确率高于自动解析的 HTML chunks
- 关键词匹配足够覆盖常见用法指导场景
- 无 embedding 模型加载和 ChromaDB 索引构建的冷启动开销

**匹配逻辑**:
- 按模板 id、name、description 做关键词匹配（各词出现 +1 分）
- `@concept` 匹配（术语或解释中出现关键词 +2 分）
- `@note` 匹配（+1 分）
- 按得分降序取 Top-3 候选模板
- 无匹配时 fallback 到 LLM 参数知识回答

**设计**: ADR-0001, plan-templates.md DC-0055, plan-llm.md DC-0035

---

## 4. 集成测试设计

### 4.1 测试目录结构

```
tests/
├── unit/                    # 已有：21 个测试文件
└── integration/             # 新建
    ├── conftest.py          # 集成测试 fixtures（真实模板目录、mock LLM）
    ├── test_init_chain.py   # T-INT-01: 初始化链
    ├── test_idle_to_preview.py  # T-INT-02: IDLE → SCRIPT_PREVIEW 完整流程
    ├── test_qa_flow.py      # T-INT-03: 问答流程
    ├── test_error_recovery.py   # T-INT-04: 错误恢复
    └── test_end_to_end.py   # T-INT-05: 端到端验收（dry-run 模式）
```

### 4.2 测试 fixtures（`conftest.py`）

```python
@pytest.fixture(scope="session")
def real_template_dir() -> Path:
    """Return the actual template directory used in production."""
    return Path(__file__).parent.parent.parent / "src" / "data" / "templates"

@pytest.fixture
def mock_llm_client() -> MagicMock:
    """LLMClient whose chat() returns configurable responses."""
    client = MagicMock()
    client.chat.return_value = "{}"  # default empty JSON
    return client

```

### 4.3 测试用例清单

#### T-INT-01: 初始化链验证

```python
def test_init_chain_builds_all_components(real_template_dir: Path) -> None:
    """All components can be instantiated with real template directory."""
```

验证：
- `scan_templates()` 能正确扫描真实模板目录
- `TemplateRegistry` 能从扫描结果构建
- `TemplateEngine` 能加载所有模板文件
- `SessionProcessor` 能组装所有依赖

#### T-INT-02: IDLE → SCRIPT_PREVIEW 完整流程

```python
def test_idle_to_preview_with_real_template(
    real_template_dir: Path,
    mock_llm_client: MagicMock,
) -> None:
    """Simulate: user asks for shp2geojson → params provided → script rendered."""
```

验证：
- 第一轮输入（任务描述）→ `IDLE` → `PARAM_COLLECT`
- 第二轮输入（参数）→ `PARAM_COLLECT` → `SCRIPT_PREVIEW`
- 脚本内容包含预期的 GDAL 命令
- 所有参数正确注入模板

#### T-INT-03: 问答流程

```python
def test_qa_flow_routes_to_answer_question(
    mock_llm_client: MagicMock,
) -> None:
    """Simulate: user asks about SHP format → template match → answer returned."""
```

验证：
- `classify_intent` 返回 `__qa__`
- `_find_matching_templates()` 根据关键词匹配模板元数据
- `answer_question()` 被调用，传入匹配的模板列表
- 响应包含答案文本
- 状态保持在 `IDLE`

#### T-INT-04: 错误恢复

```python
def test_error_recovery_after_invalid_param(
    mock_llm_client: MagicMock,
) -> None:
    """Simulate: user provides invalid param → error message → corrected → success."""
```

验证：
- 无效参数 → 校验失败 → 保持在 `PARAM_COLLECT`
- 修正参数 → 校验通过 → 进入 `SCRIPT_PREVIEW`

#### T-INT-05: 端到端验收（dry-run）

```python
def test_end_to_end_dry_run(real_template_dir: Path) -> None:
    """Full REPL session: input → classify → params → preview → dry-run skip."""
```

验证：
- REPL 在 `--dry-run` 模式下启动
- 用户输入任务描述
- 系统引导参数收集
- 脚本预览展示正确内容
- dry-run 模式跳过执行，直接返回 `IDLE`

---

## 5. 模板补充计划

### 5.1 现有模板（3个）

| ID | 名称 | 类型 |
|----|------|------|
| shp2geojson | Shapefile 转 GeoJSON | vector |
| clip_raster | 栅格裁剪 | raster |
| info_query | 数据信息查询 | general |

### 5.2 新增模板（7个）

| ID | 名称 | 类型 | 对应 GDAL 命令 |
|----|------|------|---------------|
| reproject | 重投影 | vector | `ogr2ogr -t_srs` |
| merge_shp | 合并 Shapefile | vector | `ogr2ogr -append` |
| tif2png | GeoTIFF 转 PNG | raster | `gdal_translate -of PNG` |
| warp_reproject | 栅格重投影 | raster | `gdalwarp -t_srs` |
| raster_info | 栅格信息查询 | raster | `gdalinfo` |
| buffer | 矢量缓冲区 | vector | `ogr2ogr -dialect sqlite -sql "SELECT ST_Buffer..."` |
| dissolve | 矢量融合 | vector | `ogr2ogr -dialect sqlite -sql "SELECT ST_Union..."` |

**新增后覆盖**：
- 矢量：shp2geojson, reproject, merge_shp, buffer, dissolve, info_query（6个）
- 栅格：clip_raster, tif2png, warp_reproject, raster_info（4个）
- 总计：10 个模板

### 5.3 模板文件规范

沿用已有注释头格式：

```jinja2
{# @id tif2png #}
{# @name GeoTIFF 转 PNG #}
{# @description 将 GeoTIFF 栅格数据转换为 PNG 格式 #}
{# @param input file_path required 输入 GeoTIFF 路径 #}
{# @param output file_path required 输出 PNG 路径 #}

@echo off
REM Generated by GIS Agent
REM Template: tif2png

gdal_translate -of PNG {{ input | safe_path | quote }} {{ output | safe_path | quote }}

REM Done
```

---

## 6. 数据流与控制流

### 6.1 集成测试数据流

```
[test_idle_to_preview]
    │
    ▼
fixtures: 真实模板目录 + mock LLM
    │
    ▼
SessionProcessor(registry=真实注册表, validator=真实校验器,
                 template_engine=真实引擎, llm_client=mock,
                 prompt_builder=真实)
    │
    ├──→ Round 1: process(IDLE, "把 roads.shp 转成 GeoJSON")
    │       │
    │       ├──→ mock classify_intent → IntentResult("shp2geojson", 0.95)
    │       │
    │       └──→ assert state == PARAM_COLLECT
    │
    ├──→ Round 2: process(PARAM_COLLECT, "输入 roads.shp，输出 out.json")
    │       │
    │       ├──→ mock extract_params → {input: "roads.shp", output: "out.json"}
    │       │
    │       ├──→ 真实 ParamValidator.validate_all() → 通过
    │       │
    │       ├──→ 真实 TemplateEngine.render() → RenderedScript
    │       │       │
    │       │       ├──→ Jinja2 加载 vector/shp2geojson.j2
    │       │       ├──→ safe_path 过滤器解析路径
    │       │       ├──→ quote 过滤器 shell-escape
    │       │       └──→ ScriptSecurityChecker 验证无危险字符
    │       │
    │       └──→ assert state == SCRIPT_PREVIEW
    │               assert "ogr2ogr" in response
    │               assert "roads.shp" in response
    │
    └──→ teardown
```

### 6.2 Q&A 数据流（模板元数据匹配）

```
[test_qa_flow]
    │
    ▼
fixtures: mock LLM + 真实模板注册表
    │
    ▼
SessionProcessor(registry=真实注册表, validator=真实校验器,
                 template_engine=真实引擎, llm_client=mock,
                 prompt_builder=真实)
    │
    ▼
Round 1: process(IDLE, "shp格式是什么")
    │
    ├──→ mock classify_intent → IntentResult("__qa__", 0.88)
    │
    ├──→ _find_matching_templates("shp格式是什么", top_n=3)
    │       ├──→ 关键词匹配模板 id/name/description
    │       ├──→ 匹配 @concept 元数据
    │       └──→ 返回 [shp2geojson_def, merge_shp_def, ...]
    │
    ├──→ answer_question("shp格式是什么", templates=[shp2geojson_def, ...], ...)
    │       ├──→ 提取模板元数据作为上下文
    │       └──→ 返回 "SHP（Shapefile）是 ESRI 开发的矢量数据格式..."
    │
    └──→ assert state == IDLE（问答不改变状态）
```

### 6.3 端到端验收数据流（dry-run）

```
[test_end_to_end_dry_run]
    │
    ▼
启动: python -m cli --dry-run --workspace ./test_workspace
    │
    ▼
main() 初始化链
    │
    ▼
REPL.run(Session())
    │
    ├──→ mock_input = ["roads.shp 转成 GeoJSON", "输入 roads.shp 输出 out.json"]
    │
    ├──→ "roads.shp 转成 GeoJSON"
    │       ├──→ processor.process(IDLE, ...) → PARAM_COLLECT
    │       └──→ output: "已识别任务：Shapefile 转 GeoJSON。\n\n请输入以下参数：\n  • input（必填）：..."
    │
    ├──→ "输入 roads.shp 输出 out.json"
    │       ├──→ processor.process(PARAM_COLLECT, ...) → SCRIPT_PREVIEW
    │       └──→ output: "脚本预览：...\n确认执行？(Y/N)："
    │
    ├──→ state == SCRIPT_PREVIEW → _handle_execution()
    │       ├──→ dry_run=True → preview() + "dry-run 模式，跳过执行。"
    │       └──→ state → IDLE
    │
    └──→ assert 输出中包含预期的脚本内容
```

---

## 7. 启动体验修复

### 7.1 README 修正项

| 当前 README 描述 | 问题 | 修正 |
|-----------------|------|------|
| `cd SourceCode; gis-agent` | Windows bash 下 `gis-agent` 不可用 | 改为 `cd SourceCode && python -m cli` |
| `cp SourceCode/config/config.json.template ...` | 路径描述不清楚 | 改为 `cd SourceCode && cp config/config.json.template config/config.json` |
| 未提及 `--dry-run` 的推荐用法 | 用户首次使用应推荐 dry-run | 增加 "首次使用建议：`python -m cli --dry-run`" |

### 7.2 启动路径验证

集成测试中增加：

```python
def test_launch_from_sourcecode_directory() -> None:
    """Verify `python -m cli` works when cwd is SourceCode/."""
    # This test validates the import path resolution
```

---

## 8. 质量门禁

### 8.1 代码检查

```bash
cd SourceCode
ruff format src/ tests/
ruff check src/ tests/
mypy --strict src/
```

### 8.2 测试覆盖

```bash
# 单元测试（快速）
pytest tests/unit/ -v

# 集成测试（涉及真实模板文件）
pytest tests/integration/ -v

# 全部
pytest tests/ -v
```

### 8.3 验收标准

| 编号 | 验收项 | 通过标准 |
|:----:|--------|---------|
| AC-I1 | 集成测试全部通过 | `pytest tests/integration/` 0 failures |
| AC-I2 | 模板数量 | `scan_templates()` 返回 ≥ 10 个模板 |
| AC-I3 | dry-run 端到端 | 输入任务描述 → 参数收集 → 脚本预览 → dry-run 跳过，全流程无异常 |
| AC-I4 | 问答端到端 | 输入 "ogr2ogr 是什么" → 返回模板元数据增强答案，状态保持 IDLE |
| AC-I5 | README 与代码一致 | README 中的启动指令在实际环境中可执行 |

---

## 9. 实施顺序

```
Phase 1: 基建设施
├── T-INT-01 测试框架搭建（conftest.py + fixtures）
└── 修复 README 启动指令

Phase 2: 模板补充
├── 编写 7 个新 .j2 模板文件
└── 验证 scanner 正确解析所有模板

Phase 3: 集成测试编写
├── T-INT-02: IDLE → SCRIPT_PREVIEW
├── T-INT-03: 问答流程
├── T-INT-04: 错误恢复
└── T-INT-05: 端到端 dry-run

Phase 4: 验收
├── 本地手动验证：启动 → 任务 → 参数 → 预览 → dry-run
├── 本地手动验证：启动 → 问答 → 回答
├── 运行全部测试
└── ruff + mypy 通过
```

---

## 10. 依赖关系

### 向上依赖

| 模块 | 接口 | 用途 |
|------|------|------|
| `tests/integration/conftest.py` | `scan_templates`, `TemplateEngine`, `ParamValidator`, `SessionProcessor` | 集成测试 fixture 组装 |
| `tests/integration/test_*.py` | `SessionProcessor.process()`, `REPL.run()` | 驱动状态机流转 |

### 向下暴露

集成测试不向下暴露接口，仅验证现有模块的衔接。

---

## 11. 异常与错误处理

| 异常/场景 | 触发条件 | 处理策略 |
|---------|---------|---------|
| 模板文件缺失 | 新增模板引用了不存在的文件 | 集成测试 `test_init_chain` 捕获，启动时失败 |
| mock LLM 返回无效 JSON | 测试 fixture 配置错误 | 集成测试中抛 `LLMResponseError`，assert 异常类型 |
| Jinja2 渲染失败 | 模板语法错误或参数缺失 | `TemplateEngine` 抛 `RenderError`，测试中 assert 异常 |
| 真实模板目录路径错误 | `real_template_dir` fixture 路径错误 | 集成测试 collection 阶段失败，需修正 fixture |

---

## 12. 需求追溯表

| 需求 ID | 设计决策 | 代码位置 | 说明 |
|:-------:|:--------:|:--------:|------|
| F1 | DC-0071 | `test_qa_flow.py` | 模板元数据问答集成验证 |
| F2 | DC-0071 | `test_idle_to_preview.py` | 意图分类 + 模板映射集成验证 |
| F3 | DC-0071 | `test_idle_to_preview.py` | 参数抽取 + 校验集成验证 |
| F4 | DC-0071 | `test_idle_to_preview.py` | 模板渲染集成验证 |
| F5 | DC-0073 | `test_end_to_end.py` | 脚本预览 + dry-run 验证 |
| F6 | DC-0073 | `test_end_to_end.py` | dry-run 模式端到端验证 |
| I1 | DC-0072 | `data/templates/` | 模板数量从 3 增至 10 |
| I4 | DC-0070 | `README.md` | 启动指令修正 |
| P1 | DC-0071 | `test_idle_to_preview.py` | 模板渲染（非字符串拼接）验证 |
| P2 | DC-0073 | `test_end_to_end.py` | 先展后行流程验证 |
| I6 | DC-0074 | `test_qa_flow.py`, `core/processor.py` | 模板元数据匹配问答 |

---

## 附录：变更记录

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.2.0 | 2026-05-28 | RAG 运行时移除（ADR-0001），DC-0074 改为模板元数据匹配策略；移除 retriever 引用，更新 §2.1、§3、§4.2、§4.3、§6、§8.3、§12 |
| v1.1.0 | 2026-05-28 | 新增 DC-0074：Q&A 关键词提炼 + 多路召回策略；更新 §2.1 状态机链路、§4.3 T-INT-03、§6 Q&A 数据流、§12 需求追溯表 |
| v1.0.0 | 2026-05-28 | 初版，定义集成测试基建设施、模板补充计划、端到端验收策略、启动体验修复 |
