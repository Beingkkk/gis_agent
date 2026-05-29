# tasks-adr-0001 — 移除 RAG 子系统，知识源迁移至 J2 模板元数据

| 项目 | 内容 |
|------|------|
| 来源 ADR | [ADR-0001](../Document/ADR-0001-remove-rag.md) |
| 关联 Plan | [plan-llm](../Document/plan-llm.md) v1.1.0+, [plan-templates](../Document/plan-templates.md) v1.1.0+ |
| 状态 | **已完成** |
| 创建日期 | 2026-05-28 |
| 完成日期 | 2026-05-29 |

---

## Phase 1: 清理 rag/ 运行时模块

| 任务 ID | 任务名称 | 关联设计决策 | 优先级 | 状态 |
|:-------:|---------|:----------:|:------:|:----:|
| A1-01 | 删除 `src/rag/` 运行时目录（保留 `preprocess.py` 作为开发工具） | ADR-0001 | P0 | **已完成** |
| A1-02 | 删除 `tests/unit/test_rag.py` | ADR-0001 | P0 | **已完成** |
| A1-03 | 删除 `tests/unit/test_retriever.py` | ADR-0001 | P0 | **已完成** |
| A1-04 | 更新 `pyproject.toml`：移除 `chromadb`、`sentence-transformers` | P5 | P0 | **已完成** |
| A1-05 | 更新 `config.json.template`：移除 RAG/embedding 配置段 | — | P0 | **已完成** |
| A1-06 | 更新 `config.py`：移除 RAG/embedding 相关配置字段 | — | P0 | **已完成** |

---

## Phase 2: 扩展模板数据模型与扫描器

| 任务 ID | 任务名称 | 关联设计决策 | 优先级 | 状态 |
|:-------:|---------|:----------:|:------:|:----:|
| A1-07 | 编写 scanner 扩展单元测试（TDD） | DC-0055 | P0 | **已完成** |
| A1-08 | 扩展 `TemplateDef` dataclass：新增 `concepts`/`notes`/`seealso`/`common_errors` | DC-0055 | P0 | **已完成** |
| A1-09 | 扩展 `scanner.parse_j2_header()`：解析 `@concept`/`@note`/`@seealso`/`@common_error` | DC-0055 | P0 | **已完成** |
| A1-10 | 为现有 `.j2` 模板补充知识元数据标签 | DC-0055 | P1 | **已完成** |

---

## Phase 3: 重写 llm/ 问答逻辑

| 任务 ID | 任务名称 | 关联设计决策 | 优先级 | 状态 |
|:-------:|---------|:----------:|:------:|:----:|
| A1-11 | 编写新的 `answer_question()` 单元测试（TDD） | F1, P4 | P0 | **已完成** |
| A1-12 | 删除 `llm/keywords.py`（`extract_keywords`） | ADR-0001 | P0 | **已完成** |
| A1-13 | 重写 `llm/qa.py` 中的 `answer_question()` | F1, P4 | P0 | **已完成** |
| A1-14 | 更新 `PromptBuilder.build_system_prompt()`：移除 `rag_context`，新增 `template_context` | DC-0035 | P0 | **已完成** |

---

## Phase 4: 更新 core/ 处理器

| 任务 ID | 任务名称 | 关联设计决策 | 优先级 | 状态 |
|:-------:|---------|:----------:|:------:|:----:|
| A1-15 | 更新 `SessionProcessor`：移除 `retriever` 依赖注入 | ADR-0001 | P0 | **已完成** |
| A1-16 | 更新 Q&A 状态路由：从 RAG 检索改为模板匹配 | F1 | P0 | **已完成** |
| A1-17 | 编写 processor Q&A 路由单元测试 | F1 | P0 | **已完成** |

---

## Phase 5: 更新 cli/ 启动流程

| 任务 ID | 任务名称 | 关联设计决策 | 优先级 | 状态 |
|:-------:|---------|:----------:|:------:|:----:|
| A1-18 | 更新 `cli/main.py`：移除 RAG 初始化（`get_retriever()`） | ADR-0001 | P0 | **已完成** |
| A1-19 | 更新 `cli/repl.py`：移除 RAG 就绪状态检查 | ADR-0001 | P0 | **已完成** |
| A1-20 | 更新 `cli/commands.py`：移除 `/status` 中 RAG 状态展示 | ADR-0001 | P1 | **已完成** |

---

## Phase 6: 设计文档对齐

| 任务 ID | 任务名称 | 关联设计决策 | 优先级 | 状态 |
|:-------:|---------|:----------:|:------:|:----:|
| A1-21 | 重写 `Document/plan-rag.md`：标记废弃，保留 preprocess-only 文档 | ADR-0001 | P0 | **已完成** |
| A1-22 | 更新 `Document/plan-config.md`：移除 embedding/rag 配置设计 | ADR-0001 | P0 | **已完成** |
| A1-23 | 更新 `Document/plan-cli.md`：移除 RAG 初始化 | ADR-0001 | P0 | **已完成** |
| A1-24 | 更新 `Document/plan-llm.md`：移除 RAG 上下文引用 | ADR-0001 | P0 | **已完成** |
| A1-25 | 更新 `Document/plan-integration.md`：移除 retriever 引用，更新 Q&A 数据流 | ADR-0001 | P0 | **已完成** |
| A1-26 | 更新 `Document/ADR-0001-remove-rag.md`：修正 preprocess.py 保留说明 | — | P0 | **已完成** |

---

## Phase 7: 质量门禁

| 任务 ID | 任务名称 | 关联设计决策 | 优先级 | 状态 |
|:-------:|---------|:----------:|:------:|:----:|
| A1-27 | 运行 `ruff format src/ tests/` | — | P0 | **已完成** |
| A1-28 | 运行 `ruff check src/ tests/` | — | P0 | **已完成** |
| A1-29 | 运行 `mypy --strict src/` | — | P0 | **已完成** |
| A1-30 | 运行 `pytest tests/unit/ -v` | TDD-5 | P0 | **已完成** |
| A1-31 | 验证启动时间 < 2 秒 | 8.2 | P0 | **已完成** |

---

## 编码顺序（已执行）

```
A1-01~06 (清理) → A1-07~10 (扩展模板) → A1-11~14 (重写 llm)
  → A1-15~17 (更新 core) → A1-18~20 (更新 cli) → A1-21~26 (文档对齐)
  → A1-27~31 (门禁)
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
