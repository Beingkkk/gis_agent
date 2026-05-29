# ADR-0001: 移除 RAG 子系统，知识源迁移至 J2 模板元数据

## 状态

- 提议

## 上下文

系统当前通过 RAG（检索增强生成）管道为问答（Q&A）功能提供知识支撑：

- 预处理 GDAL 官方 HTML 文档为 9706 个语义 chunks
- 使用 `paraphrase-multilingual-MiniLM-L12-v2` 编码查询向量
- 通过 ChromaDB 进行相似度检索，召回 Top-K chunks 注入 LLM Prompt

实际使用中暴露出以下结构性问题：

1. **知识覆盖错位**：GDAL HTML 文档假设读者已具备基础 GIS 概念（如 TIF、EPSG），其内容聚焦"高级用法"而非"入门解释"。用户高频提问"TIF 是什么"时，RAG 无法召回有效上下文，LLM 反而凭参数知识能准确回答。

2. **用法指导不准**：RAG 检索到的是文档中的泛泛描述，而系统执行能力的核心在 J2 模板——模板中的 `@param` 元数据和模板体才是经过验证的、可执行的确切用法。RAG 描述"可以用 ogr2ogr 转 GeoJSON"，模板直接告诉你确切的参数顺序和转义规则。

3. **运行时成本高**：ChromaDB 索引构建、embedding 模型加载、5.9MB chunks 文件维护，构成了显著的启动开销和部署复杂度。该成本无法被其实际贡献 justify。

4. **知识与行动分离**：RAG 检索到的内容和 Agent 能执行的模板是两个独立系统。RAG 能回答的，Agent 不一定能执行；Agent 能执行的，RAG 不一定检索得到。

## 决策

1. **移除 `rag/` 运行时模块**。`rag/retriever.py` 及 ChromaDB 相关代码全部删除。`rag/preprocess.py` 保留作为开发工具（HTML 文本提取，用于 J2 模板批量生成），不参与运行时。

2. **知识源迁移至 J2 模板元数据**。系统的本地知识唯一来源为 `data/templates/` 下的 `.j2` 文件及其注释头。模板同时承载"可执行脚本"和"结构化知识卡片"双重角色。

3. **扩展模板注释格式**。在现有 `@id`、`@name`、`@description`、`@param` 基础上，新增元数据标签：
   - `@concept <术语> — <解释>`：定义模板涉及的基础概念（如 GeoTIFF、重采样）
   - `@note <提示>`：使用该命令的前提条件或注意事项
   - `@common_error "<错误文本>" — <原因与修复>`：记录常见错误及处理建议
   - `@seealso <template_id>`：关联相关模板

4. **Q&A 分层策略**：
   - **基础概念问题**（如"TIF 是什么"）：直接由 LLM 参数知识回答，不检索任何本地知识库
   - **用法指导问题**（如"怎么把 SHP 转成 GeoJSON"）：基于匹配模板的 `@param`、`@description`、`@note` 生成回答
   - **错误诊断问题**：基于模板 `@common_error` + LLM 推理生成修复建议

5. **保留开发素材，不纳入运行时**。`SourceCode/data/gdal-docs-chunks.json` 保留作为后续批量生成/维护 J2 模板时的输入素材（独立工具，非运行时组件）。该文件及原始 HTML 文档不参与 Agent 运行时知识管道。

## 后果

### 正面影响

- **架构简化**：去掉 ChromaDB + embedding 模型后，生产依赖从 3 项核心 + 1 项扩展缩减为 `anthropic` + `jinja2`
- **启动提速**：消除 embedding 模型加载和 ChromaDB 索引构建的冷启动开销
- **知识质量提升**：用法类问答基于人工验证的模板元数据，准确率高于自动解析的 HTML chunks
- **知识行动一致**：用户得到的回答与其后可执行的脚本同源，降低"说得对但做不了"的风险
- **离线部署更轻量**：无需携带 5.9MB chunks 文件和 embedding 模型权重

### 负面影响 / 风险

| 风险 | 说明 | 缓解措施 |
|------|------|---------|
| GDAL 版本细节丢失 | RAG 能检索的特定版本参数变更、driver 创建选项列表等细节，模板体系可能覆盖不全 | 在开发新模板时以 HTML 文档为参考，将关键参数编码进 `@param` 和 `@note`；对极特殊场景承认系统无法回答 |
| 模板维护成本上升 | 每新增/修改一个 GDAL 命令的用法，需要同步更新模板元数据 | 模板维护与模板开发同步进行，作为开发流程的一部分 |
| LLM 参数知识幻觉 | 基础概念类问题完全依赖 LLM 参数知识，存在训练数据截止日期风险 | GDAL 核心概念（如坐标系、格式标准）变化极慢；对具体版本细节的问题引导用户到模板用法 |

### 迁移成本

| 层面 | 工作量 | 说明 |
|------|--------|------|
| 代码删除 | 中 | 删除 `rag/` 模块（retriever、preprocess、单元测试），清理 `llm/` 中 `extract_keywords`、`answer_question`，更新 `processor` Q&A 路由 |
| 代码新增 | 小 | 新增基于模板元数据的 Q&A 逻辑（模板匹配 + 元数据提取 + Prompt 组装） |
| 配置清理 | 小 | 从 `pyproject.toml` 移除 `chromadb`、`sentence-transformers`，清理 `config.json.template` 中 RAG 配置 |
| 模板扩展 | 中 | 为现有模板逐步补充 `@concept`、`@note`、`@common_error` 等元数据 |
| 文档更新 | 大 | 更新 `spec.md`（F1、P4、P5、依赖栈）、`constitution.md`（架构分层、依赖规则、CODE-4）、废弃 `plan-rag.md`、更新 `plan-llm.md` 和 `plan-templates.md` |

## 替代方案

### 替代方案 A：保留 RAG，优化检索质量

保留现有 RAG 管道，通过以下方式提升准确率：
- 换用更强的 embedding 模型
- 引入重排序（rerank）层
- 增加查询改写/扩展策略

**否决理由**：根因不是检索质量差，而是知识源（GDAL HTML 文档）与用户需求之间存在结构性错位。HTML 文档不解释基础概念，也不直接对应可执行命令。投入更多工程优化检索，无法解决知识源本身的覆盖问题。

### 替代方案 B：混合方案（RAG + 模板同时作为知识源）

保留 RAG 处理"GDAL 版本细节"类问题，同时引入模板元数据回答"用法指导"类问题。

**否决理由**：RAG 的维护成本（ChromaDB、embedding、chunks 管理、启动开销）与其能覆盖的边际场景（版本细节查询）不成比例。为了少量低频场景保留整套基础设施，不符合 P5"依赖极简"原则。

## 相关文档

- `Document/spec.md` — 需求项 F1、原则 P4/P5、依赖栈 4.1
- `Document/constitution.md` — 分层架构 6.1、依赖规则 6.2、安全原则 9.1
- `Document/plan-rag.md` — 将被标记为废弃
- `Document/plan-llm.md` — 需移除 RAG 相关设计决策
- `Document/plan-templates.md` — 需扩展模板注释格式设计
