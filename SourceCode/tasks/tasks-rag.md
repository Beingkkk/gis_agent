# tasks-rag — RAG 模块实现任务清单

| 项目 | 内容 |
|------|------|
| 来源 Plan | ~~[plan-rag](../Document/plan-rag.md)~~ 已废弃（见 ADR-0001） |
| 状态 | **已废弃** |
| 创建日期 | 2026-05-27 |

---

## 实现顺序

本模块采用**先预处理后 RAG**的串行策略：

- **Phase 1**（预处理）：完成 HTML→JSON chunks 的转换
- **Phase 2**（RAG 检索）：基于 JSON chunks 实现 ChromaDB 检索

---

## Phase 1: 预处理脚本

| 任务 ID | 任务名称 | 关联设计决策 | 优先级 | 状态 |
|:-------:|---------|:----------:|:------:|:----:|
| R-01 | 创建 `rag/` 模块目录与 `__init__.py` | — | P0 | 待办 |
| R-02 | 编写预处理模块单元测试（TDD） | DC-0020, DC-0021 | P0 | 待办 |
| R-03 | 实现 HTML 文本提取（html.parser） | DC-0020 | P0 | 待办 |
| R-04 | 实现语义切分与长度限制 | DC-0021 | P0 | 待办 |
| R-05 | 实现目录扫描与文件过滤 | DC-0025 | P0 | 待办 |
| R-06 | 实现 JSON chunks 输出 | DC-0025 | P0 | 待办 |
| R-07 | 创建 CLI 脚本 `scripts/preprocess_docs.py` | — | P0 | 待办 |
| R-08 | 运行脚本生成 `gdal-docs-chunks.json` | DC-0025 | P0 | 待办 |
| R-09 | Phase 1 质量门禁检查 | — | P0 | 待办 |

---

## Phase 2: RAG 检索模块

| 任务 ID | 任务名称 | 关联设计决策 | 优先级 | 状态 |
|:-------:|---------|:----------:|:------:|:----:|
| R-10 | 编写 RAG 单元测试（TDD） | DC-0022~0024 | P0 | 待办 |
| R-11 | 实现数据模型（DocumentChunk, RetrievedDocument） | — | P0 | 待办 |
| R-12 | 实现 `DocumentRetriever` 初始化与索引构建 | DC-0022, DC-0023, DC-0024 | P0 | 待办 |
| R-13 | 实现 `DocumentRetriever.search()` 语义检索 | DC-0021 | P0 | 待办 |
| R-14 | 实现 `get_retriever()` 单例访问 | DC-0024 | P0 | 待办 |
| R-15 | Phase 2 质量门禁检查 | — | P0 | 待办 |

---

## R-01: 创建 `rag/` 模块目录与 `__init__.py`

**关联设计决策**: 模块初始化

创建以下目录和文件：
- `SourceCode/src/rag/__init__.py`
- `SourceCode/src/rag/preprocess.py`
- `SourceCode/tests/unit/test_preprocess.py`
- `scripts/preprocess_docs.py`（开发工具）

**验收标准**:
- `from rag.preprocess import ...` 可正常导入
- `scripts/` 目录创建完成

---

## R-02: 编写预处理模块单元测试（TDD）

**关联设计决策**: DC-0020（html.parser）, DC-0021（语义切分）

**测试场景**:

| 测试类 | 测试用例 | 验证点 |
|--------|---------|--------|
| `TestHTMLExtract` | `test_extract_title` | 从 `<title>` 提取文档标题 |
| `TestHTMLExtract` | `test_extract_headings` | 按 `<section>` + `<h1>`-`<h6>` 提取语义块 |
| `TestHTMLExtract` | `test_remove_noise` | 去除导航栏、脚本、样式等噪音 |
| `TestHTMLExtract` | `test_extract_from_real_gdal_html` | 从真实 ogr2ogr.html 提取内容 |
| `TestChunkSplit` | `test_no_split_within_size` | 不超过 chunk_size 的块不二次切分 |
| `TestChunkSplit` | `test_split_long_content` | 超长内容按固定长度+overlap 切分 |
| `TestChunkSplit` | `test_overlap_preserves_context` | 重叠区域保留上下文 |
| `TestChunkSplit` | `test_chunk_id_format` | ID 格式为 `{文件名}-{序号}` |
| `TestFileFilter` | `test_include_patterns` | `programs/*.html` 匹配正确 |
| `TestFileFilter` | `test_exclude_patterns` | `api/**` 排除正确 |
| `TestJSONOutput` | `test_output_structure` | JSON 符合 §3 格式规范 |
| `TestJSONOutput` | `test_token_estimate` | token_estimate 为合理正整数 |

---

## R-03: 实现 HTML 文本提取（html.parser）

**关联设计决策**: DC-0020

实现 `extract_text_from_html(html_content: str) -> list[dict]`:
- 使用 `html.parser.HTMLParser`
- 定位 `<div role="main" class="document">` 或 `<div itemprop="articleBody">`
- 提取 `<title>` 文本
- 按 `<section>` 标签划分语义块
- 提取每个 section 下的第一个 heading 作为 section 名
- 去除 `<script>`, `<style>`, `<nav>` 等噪音标签内容
- 保留 `<pre>` 中的命令示例（去标签但保留换行）

**输出格式**:
```python
[
    {
        "title": "ogr2ogr",
        "section": "Synopsis",
        "content": "Usage: ogr2ogr [--help]...",
    },
    ...
]
```

---

## R-04: 实现语义切分与长度限制

**关联设计决策**: DC-0021

实现 `split_into_chunks(sections, chunk_size=512, chunk_overlap=128)`:

**双层策略**:
1. **第一层**：按标题切分（一个 section = 一个候选 chunk）
2. **第二层**：对超过 `chunk_size * 1.5`（768 字符）的块，按固定长度+overlap 二次切分

**约束**:
- 切分优先在段落边界（`\n\n`）或句子边界（`.` + 空格）
- 命令示例块（`<pre>` 内容）尽量保持完整
- 每个 chunk 的 `token_estimate = len(content) // 4`（粗略估计）

---

## R-05: 实现目录扫描与文件过滤

**关联设计决策**: DC-0025

实现文件扫描逻辑：
- `source_dir`: `Document/Resource/gdal/build/doc/build/html/`
- `include_patterns`: `["programs/*.html", "drivers/**/*.html"]`
- `exclude_patterns`: `["api/**", "_*/**", "genindex.html", "search.html"]`

使用 `pathlib.Path.glob()` 进行模式匹配。

---

## R-06: 实现 JSON chunks 输出

**关联设计决策**: DC-0025

实现 JSON 输出格式（plan-rag §3）：
```json
{
  "version": "1.0.0",
  "source": "GDAL 3.10.0 documentation",
  "generated_at": "2026-05-27",
  "chunks": [
    {
      "id": "ogr2ogr-001",
      "source_file": "programs/ogr2ogr.html",
      "title": "ogr2ogr",
      "section": "Synopsis",
      "content": "...",
      "token_estimate": 128
    }
  ]
}
```

输出路径：`SourceCode/data/gdal-docs-chunks.json`

---

## R-07: 创建 CLI 脚本 `scripts/preprocess_docs.py`

**说明**: 开发工具，不进入运行时依赖。

脚本功能：
- 读取默认源目录和输出路径
- 调用 `rag.preprocess.preprocess_directory()`
- 输出处理统计（文件数、chunk 数、耗时）

使用方式：
```bash
python scripts/preprocess_docs.py
```

---

## R-08: 运行脚本生成 `gdal-docs-chunks.json`

**验收标准**:
- JSON 文件成功生成在 `SourceCode/data/gdal-docs-chunks.json`
- 文件大小 < 15MB（原始 HTML 68MB 的预期缩减）
- chunk 数量在 2000~5000 之间
- 包含 `programs/` 和 `drivers/` 下的核心文档
- JSON 可被正常解析，结构符合规范

---

## R-09: Phase 1 质量门禁检查

**执行命令**:
```bash
cd SourceCode
ruff format src/rag/preprocess.py tests/unit/test_preprocess.py ../scripts/preprocess_docs.py
ruff check src/rag/preprocess.py tests/unit/test_preprocess.py ../scripts/preprocess_docs.py
mypy --strict src/rag/preprocess.py
pytest tests/unit/test_preprocess.py -v --cov=src.rag.preprocess --cov-report=term-missing
```

**门禁标准**: pytest 全通过，覆盖率 ≥80%。

---

## R-10 ~ R-15: Phase 2 详细设计

（待 Phase 1 完成后展开）
