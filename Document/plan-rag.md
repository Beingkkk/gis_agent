# plan-rag

| 项目 | 内容 |
|------|------|
| 版本 | v2.0.0 |
| 状态 | **已废弃**（RAG 运行时移除，见 ADR-0001） |
| 作者 | - |
| 日期 | 2026-05-28 |

> **注意**: 本文档原始描述的 RAG 向量检索运行时（ChromaDB + embedding）已于 2026-05-28 移除。
> `rag/` 目录现仅保留 `preprocess.py` 作为**开发工具**，用于从 GDAL HTML 文档提取结构化文本以批量生成 J2 模板。
> 本文档保留作为 preprocess 模块的设计参考，§1-5 为原始 RAG 设计（已废弃），§6 为当前 preprocess-only 接口。

---

## 1. 设计概述（历史参考）

### 1.1 原模块职责（已废弃）

构建并维护 GDAL 文档的向量检索管道：将 HTML 文档解析为结构化文本 chunks，通过 Embedding 模型编码存入 ChromaDB，提供语义检索接口供问答模块使用。

### 1.2 废弃原因

见 `Document/ADR-0001-remove-rag.md`。核心原因：
- 知识覆盖错位（HTML 文档不解释基础概念）
- 用法指导不准（检索到的泛泛描述 vs 模板中的确切参数）
- 运行时成本高（embedding 模型加载、ChromaDB 索引构建）
- 知识与行动分离（RAG 能回答的不一定能执行）

### 1.3 替代方案

Q&A 知识源迁移至 J2 模板元数据（`@concept`、`@note`、`@common_error`、`@seealso`），详见 `Document/plan-templates.md` v1.1.0+ 和 `Document/plan-llm.md` v1.1.0+。

---

## 2. 保留组件：HTML 预处理（开发工具）

### 2.1 职责

`SourceCode/src/rag/preprocess.py` 提供 GDAL HTML 文档的结构化文本提取功能。仅用于：

1. **J2 模板批量生成流水线**：`scripts/generate/extractor.py` 调用 `extract_text_from_html()` 从 GDAL HTML 提取 title、synopsis、description，供 LLM 生成 TemplateDefinition
2. **文档 chunks 生成**：`scripts/preprocess_docs.py` 调用 `preprocess_directory()` 批量处理 GDAL HTML 为 JSON chunks（`data/gdal-docs-chunks.json`），作为开发参考资料

### 2.2 不进入运行时

`preprocess.py` 及其导出函数**不**被 `cli/`、`core/`、`llm/` 运行时模块导入。它是纯开发时工具，不参与 Agent 的任何运行时流程。

---

## 3. 接口定义（当前有效）

### 3.1 数据模型

```python
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class DocumentChunk:
    """文档块（用于 chunks JSON 输出）。"""
    id: str
    source_file: str
    title: str
    section: str
    content: str
    token_estimate: int
```

### 3.2 开发工具函数

```python
from pathlib import Path
from typing import List


def extract_text_from_html(html_content: str) -> List[dict]:
    """从 GDAL HTML 中提取结构化文本段落。

    使用 html.parser.HTMLParser 解析 Sphinx 生成的 HTML，
    返回按标题分组的段落列表。

    Args:
        html_content: 原始 HTML 字符串。

    Returns:
        段落列表，每个段落包含 title、section、content 等字段。

    Design:
        DC-0020
    """


def preprocess_directory(
    source_dir: Path,
    output_path: Path,
    include_patterns: List[str],
    exclude_patterns: List[str],
    chunk_size: int = 512,
    chunk_overlap: int = 128,
) -> int:
    """批量预处理 GDAL HTML 文档目录为 JSON chunks 文件。

    Args:
        source_dir: GDAL HTML 文档根目录。
        output_path: 输出 JSON 文件路径。
        include_patterns: 包含的文件模式（如 ["programs/*.html"]。
        exclude_patterns: 排除的文件模式（如 ["api/**"]。
        chunk_size: 最大 chunk 长度（字符）。
        chunk_overlap: 切分重叠长度。

    Returns:
        生成的 chunk 数量。

    Design:
        DC-0021
    """
```

---

## 4. 数据流（当前有效）

### 4.1 J2 模板生成流水线中的 HTML 提取

```
GDAL HTML 文件
    │
    ▼
scripts/generate/extractor.py::HtmlExtractor.extract()
    │
    ├──→ extract_text_from_html(html_content)
    │       ├──→ 解析 HTML 结构（html.parser）
    │       ├──→ 提取 title、synopsis、description
    │       └──→ 返回结构化段落列表
    │
    ▼
ExtractedDoc(title, synopsis, description, options=[])
    │
    ▼
LLMTemplateGenerator.generate() → TemplateDefinition JSON
    │
    ▼
renderer.render_j2() → .j2 模板文件
```

### 4.2 开发时文档预处理

```
[开发者运行 scripts/preprocess_docs.py]
    │
    ▼
扫描 source_dir 下匹配 include_patterns 的 HTML 文件
    │
    ├──→ 逐个解析 HTML（html.parser）
    │       ├──→ 提取 <title> 作为文档标题
    │       ├──→ 按 h1-h6 切分语义块
    │       ├──→ 去除导航栏、页脚、面包屑等噪音
    │       └──→ 将表格转为 Markdown 格式文本
    │
    ├──→ 对超长块做固定长度二次切分（overlap=128）
    │
    ├──→ 生成 chunk ID：{文件名}-{序号}
    │
    └──→ 输出为 JSON 到 SourceCode/data/gdal-docs-chunks.json
```

---

## 5. 依赖关系

### 5.1 使用方（开发时）

| 模块 | 接口 | 用途 |
|------|------|------|
| `scripts/generate/extractor.py` | `extract_text_from_html()` | J2 模板生成流水线中的 HTML 文本提取 |
| `scripts/preprocess_docs.py` | `preprocess_directory()` | 批量生成开发参考用的 JSON chunks |

### 5.2 外部依赖

| 库 | 用途 | 说明 |
|---|------|------|
| `html.parser` (stdlib) | HTML 解析 | 零额外依赖，符合 P5 |

---

## 6. 测试策略

仅测试 `preprocess.py` 中的解析逻辑（`tests/unit/test_preprocess.py`）。RAG 检索相关测试已全部删除。

| 测试场景 | 验证点 |
|---------|--------|
| HTML 标题提取 | 正确解析 Sphinx HTML 的标题层级 |
| Synopsis 提取 | 从 GDAL 程序文档中正确提取命令摘要 |
| Description 提取 | 提取长描述文本 |
| 噪音过滤 | 导航栏、页脚不被包含 |
| 表格转文本 | HTML 表格转为 Markdown 格式 |
| chunk 长度限制 | 超长文本按 chunk_size 切分 |

---

## 7. 需求追溯表（历史参考）

原 RAG 设计的需求追溯。当前系统通过模板元数据满足以下需求：

| 需求 ID | 替代方案 | 说明 |
|:-------:|:--------:|------|
| F1 | `plan-templates.md` v1.1.0+ | 模板元数据 `@concept`/`@note` 回答用法问题 |
| F10 | `plan-llm.md` DC-0036 | 基于模板 `@common_error` 的错误诊断 |
| P4 | ADR-0001 | 知识仅来源于模板元数据，不检索外部文档 |
| P5 | — | 移除 chromadb、sentence-transformers，生产依赖仅 anthropic + jinja2 |

---

## 附录：变更记录

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v2.0.0 | 2026-05-28 | RAG 运行时移除，文档重写为 preprocess-only 状态。保留 §3.2 接口定义、§4 数据流、§5 依赖关系作为开发工具参考 |
| v1.1.0 | 2026-05-28 | 新增 `search_multi()` 接口（§3.2、§4.2、§7）；更新文档问答检索流程为多路召回 |
| v1.0.1 | 2026-05-27 | 新增 §9 实现顺序，明确"先预处理后 RAG"的串行策略 |
| v1.0.0 | 2026-05-26 | 初版，定义 HTML 预处理、语义切分、ChromaDB 封装、懒加载策略 |
