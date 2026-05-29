# tasks-adr-0001 — 移除 RAG 子系统，知识源迁移至 J2 模板元数据

| 项目 | 内容 |
|------|------|
| 来源 ADR | [ADR-0001](../Document/ADR-0001-remove-rag.md) |
| 关联 Plan | [plan-llm](../Document/plan-llm.md) v1.1.0+, [plan-templates](../Document/plan-templates.md) v1.1.0+ |
| 状态 | 待实现 |
| 创建日期 | 2026-05-28 |

---

## 前置条件

- ADR-0001 已批准
- spec.md、constitution.md、plan-*.md 已完成对齐

---

## Phase 1: 清理 rag/ 运行时模块

| 任务 ID | 任务名称 | 关联设计决策 | 优先级 | 状态 |
|:-------:|---------|:----------:|:------:|:----:|
| A1-01 | 删除 `src/rag/` 运行时目录（保留 `preprocess.py` 作为开发工具） | ADR-0001 | P0 | 待办 |
| A1-02 | 删除 `tests/unit/test_rag.py` | ADR-0001 | P0 | 待办 |
| A1-03 | 删除 `tests/unit/test_retriever.py` | ADR-0001 | P0 | 待办 |
| A1-04 | 更新 `pyproject.toml`：移除 `chromadb`、`sentence-transformers` | P5 | P0 | 待办 |
| A1-05 | 更新 `config.json.template`：移除 RAG/embedding 配置段 | — | P0 | 待办 |
| A1-06 | 更新 `config.py`：移除 RAG/embedding 相关配置字段 | — | P0 | 待办 |

---

## Phase 2: 扩展模板数据模型与扫描器

| 任务 ID | 任务名称 | 关联设计决策 | 优先级 | 状态 |
|:-------:|---------|:----------:|:------:|:----:|
| A1-07 | 编写 scanner 扩展单元测试（TDD） | DC-0055 | P0 | 待办 |
| A1-08 | 扩展 `TemplateDef` dataclass：新增 `concepts`/`notes`/`seealso`/`common_errors` | DC-0055 | P0 | 待办 |
| A1-09 | 扩展 `scanner.parse_j2_header()`：解析 `@concept`/`@note`/`@seealso`/`@common_error` | DC-0055 | P0 | 待办 |
| A1-10 | 为现有 `.j2` 模板补充知识元数据标签 | DC-0055 | P1 | 待办 |

---

## Phase 3: 重写 llm/ 问答逻辑

| 任务 ID | 任务名称 | 关联设计决策 | 优先级 | 状态 |
|:-------:|---------|:----------:|:------:|:----:|
| A1-11 | 编写新的 `answer_question()` 单元测试（TDD） | F1, P4 | P0 | 待办 |
| A1-12 | 删除 `llm/keywords.py`（`extract_keywords`） | ADR-0001 | P0 | 待办 |
| A1-13 | 重写 `llm/qa.py`（或更新 `llm/intent.py`/`llm/client.py`）中的 `answer_question()` | F1, P4 | P0 | 待办 |
| A1-14 | 更新 `PromptBuilder.build_system_prompt()`：移除 `rag_context`，新增 `template_context` | DC-0035 | P0 | 待办 |

---

## Phase 4: 更新 core/ 处理器

| 任务 ID | 任务名称 | 关联设计决策 | 优先级 | 状态 |
|:-------:|---------|:----------:|:------:|:----:|
| A1-15 | 更新 `SessionProcessor`：移除 `retriever` 依赖注入 | ADR-0001 | P0 | 待办 |
| A1-16 | 更新 Q&A 状态路由：从 RAG 检索改为模板匹配 | F1 | P0 | 待办 |
| A1-17 | 编写 processor Q&A 路由单元测试 | F1 | P0 | 待办 |

---

## Phase 5: 更新 cli/ 启动流程

| 任务 ID | 任务名称 | 关联设计决策 | 优先级 | 状态 |
|:-------:|---------|:----------:|:------:|:----:|
| A1-18 | 更新 `cli/main.py`：移除 RAG 初始化（`get_retriever()`） | ADR-0001 | P0 | 待办 |
| A1-19 | 更新 `cli/repl.py`：移除 RAG 就绪状态检查 | ADR-0001 | P0 | 待办 |
| A1-20 | 更新 `cli/commands.py`：移除 `/status` 中 RAG 状态展示 | ADR-0001 | P1 | 待办 |

---

## Phase 6: 质量门禁

| 任务 ID | 任务名称 | 关联设计决策 | 优先级 | 状态 |
|:-------:|---------|:----------:|:------:|:----:|
| A1-21 | 运行 `ruff format src/ tests/` | — | P0 | 待办 |
| A1-22 | 运行 `ruff check src/ tests/` | — | P0 | 待办 |
| A1-23 | 运行 `mypy --strict src/` | — | P0 | 待办 |
| A1-24 | 运行 `pytest tests/unit/ -v` | TDD-5 | P0 | 待办 |
| A1-25 | 验证启动时间 < 2 秒 | 8.2 | P0 | 待办 |

---

## 详细任务说明

### A1-01: 删除 rag/ 运行时目录

**注意**: `src/rag/preprocess.py` 保留作为开发工具（用于后续批量生成 J2 模板），但不再被运行时导入。

需要删除的文件：
- `SourceCode/src/rag/retriever.py`
- `SourceCode/src/rag/__init__.py` 中暴露的 retriever 相关 API

保留的文件：
- `SourceCode/src/rag/preprocess.py`（开发工具，不进入运行时依赖）

**验收标准**:
- `from rag.retriever import ...` 在运行时不再可用
- `from rag.preprocess import ...` 仍可在开发时导入
- `src/rag/` 目录仅含 `preprocess.py`

---

### A1-04: 更新 pyproject.toml

移除以下依赖：
```toml
# 移除
dependencies = [
    "anthropic>=0.30.0",
    "chromadb>=0.5.0",      # ← 移除
    "jinja2>=3.1.0",
]

# 移除 [project.optional-dependencies] 中的 sentence-transformers（如有）
```

同时更新 `config.py` 中的 `RAGConfig` 和 `EmbeddingConfig` dataclass。

---

### A1-07 ~ A1-09: 扩展 TemplateDef 和 Scanner

**A1-07 测试用例**:

| 测试类 | 测试方法 | 验证点 |
|--------|---------|--------|
| `TestScannerExtended` | `test_parse_concept_tag` | `{# @concept "GeoTIFF" — TIFF 的地理空间扩展 #}` → concepts=[("GeoTIFF", "TIFF 的地理空间扩展")] |
| `TestScannerExtended` | `test_parse_note_tag` | `{# @note 输出路径自动加时间戳 #}` → notes=["输出路径自动加时间戳"] |
| `TestScannerExtended` | `test_parse_seealso_tag` | `{# @seealso vector/shp2geojson #}` → seealso=["vector/shp2geojson"] |
| `TestScannerExtended` | `test_parse_common_error_tag` | `{# @common_error "Unable to open" — 检查路径是否存在 #}` → common_errors=[("Unable to open", "检查路径是否存在")] |
| `TestScannerExtended` | `test_multiple_concepts` | 多个 @concept 均被解析 |
| `TestScannerExtended` | `test_unknown_tag_ignored` | 未知标签不抛错，直接忽略 |
| `TestTemplateDefExtended` | `test_def_has_knowledge_fields` | TemplateDef 包含 concepts/notes/seealso/common_errors 字段 |

**A1-08 TemplateDef 扩展**:

```python
@dataclass(frozen=True)
class TemplateDef:
    """模板定义（来自模板注册表）。"""
    id: str
    name: str
    description: str
    template_file: str
    params: List[ParamDef]
    # 新增知识元数据字段
    concepts: List[tuple[str, str]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    seealso: List[str] = field(default_factory=list)
    common_errors: List[tuple[str, str]] = field(default_factory=list)
```

**A1-09 Scanner 扩展**:

在现有 `@id`, `@name`, `@description`, `@param` 解析基础上，新增正则：
```python
CONCEPT_PATTERN = re.compile(r'\{#\s*@concept\s+"([^"]+)"\s*—\s*(.+?)\s*#\}')
NOTE_PATTERN = re.compile(r'\{#\s*@note\s+(.+?)\s*#\}')
SEEALSO_PATTERN = re.compile(r'\{#\s*@seealso\s+(\S+)\s*#\}')
COMMON_ERROR_PATTERN = re.compile(r'\{#\s*@common_error\s+"([^"]+)"\s*—\s*(.+?)\s*#\}')
```

---

### A1-11 ~ A1-14: 重写 llm/ 问答

**A1-12 删除 `extract_keywords`**:
- 删除 `SourceCode/src/llm/keywords.py`
- 删除 `tests/unit/test_keywords.py`
- 删除 `llm/__init__.py` 中对 `extract_keywords` 的暴露

**A1-13 重写 `answer_question()`**:

```python
def answer_question(
    user_input: str,
    template_infos: List[TemplateInfo],
    history: List[Message],
    client: LLMClient,
    builder: PromptBuilder,
) -> str:
    """基于模板元数据生成问答回答。

    分层策略：
    - 若 template_infos 非空 → 基于模板元数据回答用法指导
    - 若 template_infos 为空 → 由 LLM 用参数知识回答基础概念
    """
```

**A1-14 PromptBuilder 更新**:

```python
def build_system_prompt(
    self,
    template_context: Optional[str] = None,
    task_context: Optional[str] = None,
) -> str:
    # 移除 rag_context 参数，新增 template_context
```

---

### A1-15 ~ A1-17: 更新 SessionProcessor

**A1-15 构造函数变更**:

```python
class SessionProcessor:
    def __init__(
        self,
        registry: TemplateRegistry,
        validator: ParamValidator,
        template_engine: TemplateEngine,
        llm_client: LLMClient,
        prompt_builder: PromptBuilder,
        # 移除 retriever: DocumentRetriever
    ) -> None:
```

**A1-16 Q&A 路由变更**:

原有路由（RAG 增强）：
```
用户输入 → extract_keywords → search_multi(RAG) → answer_question
```

新路由（模板知识）：
```
用户输入 → classify_intent（获取候选模板） → 提取模板元数据 → answer_question(template_context)
```

匹配逻辑：
1. 用 `classify_intent` 的相似度机制获取 Top-3 候选模板
2. 提取候选模板的 `concepts`, `notes`, `common_errors` 作为上下文
3. 传入 `answer_question()` 生成回答

---

### A1-18 ~ A1-20: 更新 CLI 启动流程

**A1-18 main.py 变更**:

```python
# 移除
from rag.retriever import get_retriever

# 移除
retriever = get_retriever()

# 移除 retriever 传给 SessionProcessor 的构造
processor = SessionProcessor(
    registry=registry,
    validator=validator,
    template_engine=template_engine,
    llm_client=llm_client,
    prompt_builder=prompt_builder,
    # retriever=retriever,  # ← 移除
)
```

---

## 编码顺序

```
A1-01~06 (清理) → A1-07~10 (扩展模板) → A1-11~14 (重写 llm) → A1-15~17 (更新 core) → A1-18~20 (更新 cli) → A1-21~25 (门禁)
```

**原因**: 模板扩展是后续所有 llm/core/cli 改动的基础（新的 `TemplateDef` 字段、scanner 解析）。

---

## 需求追溯

| 需求 ID | 设计决策 | 任务 | 说明 |
|:-------:|:--------:|:----:|------|
| F1 | DC-0055 | A1-07~14 | 模板元数据作为问答知识源 |
| F1 | DC-0035 | A1-13~14 | 问答 Prompt 组装 |
| P4 | ADR-0001 | A1-01~06 | 移除 RAG，知识仅来源于模板元数据 |
| P5 | ADR-0001 | A1-04 | 移除 chromadb、sentence-transformers |
| CODE-3 | DC-0031 | A1-13~14 | LLM 调用封装在 llm/ |
