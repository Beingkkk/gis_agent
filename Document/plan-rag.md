# plan-rag

| 项目 | 内容 |
|------|------|
| 版本 | v1.1.0 |
| 状态 | 设计基线 |
| 作者 | - |
| 日期 | 2026-05-28 |

---

## 1. 设计概述

### 1.1 模块职责

构建并维护 GDAL 文档的向量检索管道：将 HTML 文档解析为结构化文本 chunks，通过 Embedding 模型编码存入 ChromaDB，提供语义检索接口供问答模块使用。本模块是**文档问答（F1）的基础设施**。

### 1.2 所属架构层次

应用层（`rag/`）。不依赖任何上层模块，仅向外暴露检索接口。

### 1.3 对应需求项

| 需求 ID | 需求描述 |
|:-------:|---------|
| F1 | 基于本地 GDAL 官方工具文档（HTML），通过 ChromaDB 向量检索 |
| F10 | 错误诊断时检索相关文档给出修复建议 |
| P4 | RAG 仅用于检索本地官方文档，不混合网络随机内容 |
| AC-1 | 能从本地文档中检索并回答工具使用问题 |

---

## 2. 设计决策

### DC-0020: HTML 解析使用 Python 标准库 `html.parser`

**决策**: 预处理脚本使用标准库的 `html.parser.HTMLParser` 提取文本，不引入 `beautifulsoup4`。

**理由**:
- 符合 P5（依赖仅 anthropic、chromadb、jinja2）
- GDAL 文档结构规整（Sphinx 生成），标准库足以处理
- 预处理脚本属开发工具，不进入运行时依赖

**替代方案**:
- BeautifulSoup：API 更友好，但多一个依赖
- lxml：需要二进制编译，部署复杂

### DC-0021: 文档切分采用"语义切分 + 长度限制"双层策略

**决策**: 第一层按 HTML 标题（h1-h6）切分为语义块，第二层对超过 chunk_size 的块按固定长度+重叠二次切分。

**理由**:
- 按标题切分保留文档结构，检索结果上下文完整
- 固定长度切分保证 embedding 质量（过长文本语义稀释）
- 重叠（overlap）防止跨边界信息丢失

**切分参数**（来自 Config.rag）：
- `chunk_size`: 512 tokens（按字符近似，一个汉字/英文单词约 1-2 token）
- `chunk_overlap`: 128 字符
- 最大 chunk：不超过 chunk_size 的 1.5 倍（即 768）

### DC-0022: ChromaDB 使用本地持久化模式

**决策**: ChromaDB 以 SQLite 后端本地持久化，数据库存放在用户级缓存目录（`~/.cache/gis-agent/chroma/`）。

**理由**:
- 不污染 Git 仓库（二进制数据库文件不适合版本控制）
- 跨会话复用索引，满足 <3 秒启动要求
- 用户级缓存目录遵循 XDG 规范

### DC-0023: Embedding 模型从本地路径加载

**决策**: `paraphrase-multilingual-MiniLM-L12-v2` 模型文件存放在 `SourceCode/model/`，运行时通过本地路径加载，不触发网络下载。

**理由**:
- 完全零外部网络依赖（符合 P4 / P5）
- 模型随代码交付，版本可控
- 启动时无需等待下载

### DC-0024: 索引采用"内容 hash 检测 + 懒构建"策略

**决策**: 运行时检测 JSON chunks 文件的 hash，与缓存中记录对比。若一致则直接加载 ChromaDB；若不一致或首次运行则重新 embedding。

**理由**:
- 日常启动直接加载缓存，满足 <3 秒要求
- GDAL 文档更新时自动重建，无需手动干预
- hash 检测开销极低（读取一次文件 vs 全量 embedding）

### DC-0025: JSON Chunks 文件作为提交资源

**决策**: 预处理后的文档 chunks 以 JSON 文件形式存放在 `SourceCode/data/`，纳入 Git 跟踪。

**理由**:
- 文本文件可 diff、可 review
- 体积远小于原始 HTML（去除标记和噪音）
- 新环境开箱即用，无需重新解析 HTML

**JSON 格式**:
```json
{
  "version": "1.0.0",
  "source": "GDAL 3.10.0 documentation",
  "generated_at": "2026-05-26",
  "chunks": [
    {
      "id": "ogr2ogr-001",
      "source_file": "programs/ogr2ogr.html",
      "title": "ogr2ogr",
      "section": "Synopsis",
      "content": "ogr2ogr [-f format]...",
      "token_estimate": 128
    }
  ]
}
```

---

## 3. 接口定义

### 3.1 数据模型

```python
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class DocumentChunk:
    """文档块。"""
    id: str
    source_file: str
    title: str
    section: str
    content: str
    token_estimate: int


@dataclass(frozen=True)
class RetrievedDocument:
    """检索结果。"""
    chunk: DocumentChunk
    distance: float  # ChromaDB 返回的 L2 距离，越小越相关
```

### 3.2 检索器接口

```python
from typing import List, Optional


class DocumentRetriever:
    """GDAL 文档向量检索器。

    封装 ChromaDB 的初始化、索引构建和检索逻辑。
    进程内单例，通过 get_retriever() 访问。

    Design:
        DC-0021, DC-0022, DC-0023, DC-0024
    """

    def __init__(self, collection_name: str = "gdal_docs") -> None:
        """初始化检索器，自动加载或构建索引。

        首次调用时会检查缓存：
        - 缓存有效（hash 匹配）→ 直接加载
        - 缓存无效/不存在 → 读取 JSON chunks → embedding → 存入 ChromaDB

        Args:
            collection_name: ChromaDB collection 名称。
        """

    def search(self, query: str, top_k: Optional[int] = None) -> List[RetrievedDocument]:
        """语义检索与查询最相关的 GDAL 文档 chunks。

        Args:
            query: 用户查询（中文或英文）。
            top_k: 返回结果数量。默认从 Config.rag.top_k 读取。

        Returns:
            按相关性排序的文档列表（distance 升序）。

        Raises:
            RuntimeError: 索引未初始化完成。
        """

    def search_multi(
        self,
        queries: List[str],
        top_k_per_query: Optional[int] = None,
    ) -> List[RetrievedDocument]:
        """多路召回：对每个 query 分别搜索，合并去重后按 relevance 排序。

        Args:
            queries: 搜索关键词/短语列表（由 LLM 提炼）。
            top_k_per_query: 每个 query 的返回数量。默认从 Config.rag.top_k 读取。

        Returns:
            去重后的文档列表（distance 升序）。同一 chunk 在不同 query 中出现时，
            保留 distance 最小的结果。

        Raises:
            RuntimeError: 索引未初始化完成。

        Design:
            DC-0074
        """

    def is_ready(self) -> bool:
        """索引是否已就绪。"""
```

### 3.3 模块级函数

```python
def get_retriever() -> DocumentRetriever:
    """获取全局 DocumentRetriever 单例。

    Raises:
        RuntimeError: 在 ChromaDB 初始化失败时抛出。
    """
```

### 3.4 预处理脚本（开发时运行）

```python
# scripts/preprocess_docs.py —— 不进入运行时，属开发工具

def preprocess_html(
    source_dir: Path,      # Document/Resource/gdal/build/doc/build/html/
    output_path: Path,      # SourceCode/data/gdal-docs-chunks.json
    include_patterns: List[str],  # ["programs/*.html", "drivers/**/*.html"]
    exclude_patterns: List[str],  # ["api/**", "_*/**"]
) -> None:
    """将 GDAL HTML 文档预处理为 JSON chunks 文件。

    开发者在 GDAL 文档更新时手动运行此脚本。
    """
```

---

## 4. 数据流与控制流

### 4.1 首次启动索引构建流程

```
[CLI 启动]
    │
    ▼
初始化 Workspace
    │
    ▼
调用 get_retriever()
    │
    ├──→ 读取 Config.embedding.model_path
    │
    ├──→ 加载 SentenceTransformer 模型（本地）
    │       └── 失败 → RuntimeError（模型文件缺失）
    │
    ├──→ 初始化 ChromaDB PersistentClient（~/.cache/gis-agent/chroma/）
    │
    ├──→ 计算 SourceCode/data/gdal-docs-chunks.json 的 hash
    │
    ├──→ 与缓存中记录的 hash 对比
    │       │
    │       ├──→ 匹配 → 跳过构建，返回 retriever
    │       │
    │       └──→ 不匹配/无缓存 → 进入构建流程
    │               │
    │               ├──→ 读取 JSON chunks 文件
    │               ├──→ 逐 chunk 计算 embedding
    │               ├──→ 写入 ChromaDB collection
    │               ├──→ 记录当前 hash 到缓存元数据
    │               └──→ 返回 retriever
    │
    ▼
[就绪，可接受检索请求]
```

### 4.2 文档问答检索流程（多路召回）

```
用户提问："ogr2ogr 怎么转成 GeoJSON？"
    │
    ▼
LLM 提炼关键词 → ["ogr2ogr GeoJSON output", "ogr2ogr -f format", "vector conversion GDAL"]
    │
    ▼
DocumentRetriever.search_multi(["ogr2ogr GeoJSON output", "ogr2ogr -f format", "vector conversion GDAL"], top_k_per_query=2)
    │
    ├──→ search("ogr2ogr GeoJSON output", top_k=2) → [doc_A, doc_B]
    ├──→ search("ogr2ogr -f format", top_k=2) → [doc_B, doc_C]
    ├──→ search("vector conversion GDAL", top_k=2) → [doc_D, doc_E]
    │
    ├──→ 按 chunk.id 去重（doc_B 出现两次，保留更小 distance）
    ├──→ 按 distance 升序排序
    │
    └──→ 返回 List[RetrievedDocument] = [doc_B, doc_A, doc_C, doc_D, doc_E]
            │
            ▼
        返回给 LLM 模块，作为上下文注入 Prompt
```

**降级路径**：关键词提炼失败时，fallback 到原句单路搜索：
```
DocumentRetriever.search("ogr2ogr 怎么转成 GeoJSON？", top_k=5)
```

### 4.3 开发时预处理流程

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

### 5.1 向上依赖

| 模块 | 接口 | 用途 |
|------|------|------|
| `config` | `get_config()` | 读取 embedding 模型路径、rag 参数 |

### 5.2 向下暴露

| 接口 | 使用方 |
|------|--------|
| `DocumentRetriever.search()` | `llm/`（文档问答时调用） |
| `DocumentRetriever.is_ready()` | `cli/`（启动时检查状态） |
| `get_retriever()` | `llm/`、 `cli/` |

### 5.3 外部依赖

| 库 | 用途 | 版本约束 |
|---|------|---------|
| `chromadb` | 向量数据库 | 按 pyproject.toml |
| `sentence-transformers` | Embedding 模型加载 | 需评估是否额外引入（见下方讨论） |

> **关于 sentence-transformers**: ChromaDB 的默认 `DefaultEmbeddingFunction` 使用 `onnxruntime` + 本地模型文件。若直接操作 ChromaDB 的底层 embedding 接口可能无需 sentence-transformers。但为明确控制模型加载路径，建议显式使用 `SentenceTransformer` 类。这会引入 `sentence-transformers` 及其依赖（`torch`、`transformers` 等），显著增加依赖树。
>
> **替代方案**: 使用 ChromaDB 的 `EmbeddingFunction` 协议，自行实现一个轻量包装器，直接加载 ONNX 模型。这样避免 `torch` 依赖。需在 ADR 中记录此决策。

---

## 6. 异常与错误处理

| 异常类型 | 触发条件 | 处理策略 |
|---------|---------|---------|
| `RuntimeError` | 模型文件路径不存在或损坏 | CLI 启动时捕获，提示用户检查 `SourceCode/model/` 并退出 |
| `RuntimeError` | ChromaDB 初始化失败（磁盘满、权限） | 同上，提示检查 `~/.cache/gis-agent/` 权限 |
| `RuntimeError` | `search()` 在索引未完成时调用 | 内部逻辑错误，不应发生 |
| `FileNotFoundError` | JSON chunks 文件缺失 | 启动时捕获，提示运行 `scripts/preprocess_docs.py` |
| `json.JSONDecodeError` | JSON chunks 文件损坏 | 提示重新运行预处理脚本 |

---

## 7. 测试策略

### 7.1 单元测试覆盖

| 测试场景 | 验证点 |
|---------|--------|
| 检索基本功能 | 输入已知查询，返回非空结果列表 |
| 相关性排序 | 结果按 distance 升序排列 |
| top_k 限制 | 返回数量不超过配置值 |
| 中文查询 | 中文问题能检索到英文文档 |
| 空结果处理 | 无相关文档时返回空列表（不抛异常） |
| 索引就绪检查 | `is_ready()` 在构建完成后返回 True |
| **多路召回合并** | `search_multi()` 合并多 query 结果 |
| **去重逻辑** | 同一 chunk 在不同 query 中出现时保留最小 distance |
| **排序逻辑** | `search_multi()` 最终结果按 distance 升序 |

### 7.2 集成测试场景

- 端到端检索：预置小规模测试 chunks → 构建索引 → 查询 → 验证返回内容
- 缓存命中：第二次启动不重新 embedding，直接加载
- hash 变更检测：修改 JSON 文件后触发重建

### 7.3 Mock 策略

- 使用小型测试模型替代 120MB 完整模型（如加载一个维度相同的随机向量生成器）
- 使用内存 ChromaDB（`chromadb.Client()` 而非 `PersistentClient`）加速测试
- 测试 fixtures 放在 `tests/fixtures/docs/` 下

---

## 8. 需求追溯表

| 需求 ID | 设计决策 | 代码文件/函数 | 说明 |
|:-------:|:--------:|:-------------:|------|
| F1 | DC-0021, DC-0024 | `DocumentRetriever.search()` | 文档检索管道 |
| F10 | DC-0021 | `DocumentRetriever.search()` | 错误诊断文档检索 |
| P4 | DC-0020, DC-0025 | JSON chunks + 本地模型 | 仅本地文档 |
| AC-1 | DC-0021, DC-0023 | multilingual embedding | 中文查询匹配英文文档 |
| CODE-4 | — | `rag/` 模块封装 | ChromaDB 不外泄 |
| P5 | DC-0020 | `html.parser` | 零额外解析依赖 |

---

## 9. 实现顺序

本模块采用**先预处理后 RAG**的串行实现策略：

### Phase 1: 预处理脚本（先行）

| 步骤 | 任务 | 输出 | 说明 |
|------|------|------|------|
| 1 | 创建 `SourceCode/src/rag/preprocess.py` 单元测试 | `tests/unit/test_preprocess.py` | TDD：先写测试，验证 HTML 解析、标题切分、长度限制等 |
| 2 | 实现 HTML 解析与 chunk 生成逻辑 | `SourceCode/src/rag/preprocess.py` | 核心库函数，使用 `html.parser`，可被 pytest 导入测试 |
| 3 | 实现 CLI 入口脚本 | `scripts/preprocess_docs.py` | 调用 `preprocess.py`，不进入运行时 |
| 4 | 运行脚本生成 JSON | `SourceCode/data/gdal-docs-chunks.json` | 纳入 Git 跟踪的文本资源 |
| 5 | 质量检查 | — | ruff、mypy、pytest 通过；验证 JSON 结构符合 §3 格式 |

### Phase 2: RAG 检索模块

| 步骤 | 任务 | 输出 | 说明 |
|------|------|------|------|
| 6 | 创建 RAG 单元测试 | `tests/unit/test_rag.py` | 使用 Phase 1 生成的 JSON 作为测试 fixture |
| 7 | 实现 `DocumentRetriever` | `SourceCode/src/rag/retriever.py` | ChromaDB 封装、索引构建、语义检索 |
| 8 | 实现模块公开 API | `SourceCode/src/rag/__init__.py` | 暴露 `get_retriever()`、`DocumentRetriever` 等 |
| 9 | 集成验证 | — | 端到端检索测试、缓存命中测试、hash 变更检测 |

**关键约束**：
- Phase 1 的 JSON chunks 是 Phase 2 的**必要输入**，必须先完成
- `scripts/preprocess_docs.py` 为开发工具，不列入运行时依赖（P5 仍满足）
- `SourceCode/src/rag/preprocess.py` 属于 `rag/` 包的一部分，但仅开发时使用；其公开函数不暴露给上层模块

---

## 附录：变更记录

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.1.0 | 2026-05-28 | 新增 `search_multi()` 接口（§3.2、§4.2、§7）；更新文档问答检索流程为多路召回 |
| v1.0.1 | 2026-05-27 | 新增 §9 实现顺序，明确"先预处理后 RAG"的串行策略 |
| v1.0.0 | 2026-05-26 | 初版，定义 HTML 预处理、语义切分、ChromaDB 封装、懒加载策略 |
