# ADR-0003: 引入 `beautifulsoup4` 替代手写 `HTMLParser` 进行 HTML 文本提取

## 状态

- 已通过

## 上下文

`DC-0088`（plan-j2-generate.md）规定文档提取器"复用标准库实现，零额外依赖（`html.parser.HTMLParser`）"。当前项目中存在两套独立的 HTML 提取逻辑：

1. **在线模式** — `templates/extractors.py::HtmlExtractor`
   - 基于 `html.parser.HTMLParser` 手写状态机
   - 负责清洗用户上传的 HTML/Markdown 文档，提取纯文本供 LLM 生成模板
   - ~110 行，维护 `tag_stack` / `_skip_depth` / `_last_tag` 等状态

2. **CLI 批量模式** — `rag/preprocess.py::_GDALDocParser`
   - 基于 `html.parser.HTMLParser` 的复杂状态机
   - 负责从 GDAL Sphinx HTML 中提取结构化 section（标题 + Synopsis + Description）
   - ~150 行，维护 `tag_stack` / `main_depth` / `noise_depth` / `section_stack` / `in_heading` / `_in_pre` 等交织状态

实践中手写 `HTMLParser` 暴露出以下问题：

- **维护成本高**：任何新的 HTML 结构（如 GDAL 文档升级 Sphinx 主题后标签嵌套变化）都需要重新理解并修改状态机
- **可靠性差**：`tag_stack` 的 push/pop 不对称（`handle_endtag` 中 `while self.tag_stack and self.tag_stack.pop() != tag`）在标签未正确闭合时行为不可预期
- **代码膨胀**：两套提取逻辑合计 ~260 行，核心职责（"从 HTML 中提取文本"）被状态机噪音淹没
- **复用困难**：`_GDALDocParser` 的 section 分割逻辑和 `HtmlExtractor` 的噪音过滤逻辑因状态机耦合而无法互相借用

Markdown 提取 (`MarkdownExtractor`) 不涉及 HTML 解析，继续使用正则清洗，不在本 ADR 范围内。

## 决策

1. **引入 `beautifulsoup4` 作为生产依赖**。使用 `bs4.BeautifulSoup` 替代手写的 `HTMLParser` 状态机：
   - `HtmlExtractor`：使用 `soup.find_all()` 去噪音标签 + `get_text()` 提取纯文本
   - `_GDALDocParser`：使用 `soup.select()` 定位主内容区 + `find_all('section')` 分割章节

2. **保留 `MarkdownExtractor`**：Markdown 清洗逻辑以正则为主，不涉及 HTML 树遍历，不引入 `markdown` 库（该库目标是渲染为 HTML 而非提取纯文本，引入后反而增加转换链路）。

3. **接口契约不变**：
   - `HtmlExtractor.extract(html: str) -> str` 签名不变
   - `extract_text_from_html(html: str) -> list[dict[str, str]]` 签名不变
   - 现有调用方（`api/routes/generator.py`、`scripts/generate/extractor.py`）无需修改

4. **保留 `split_into_chunks` 和 `preprocess_directory`**：仅替换底层 HTML 解析器，分块策略和文件遍历逻辑不变。

## 后果

### 正面影响

| 方面 | 说明 |
|------|------|
| **代码简化** | `templates/extractors.py` 从 ~110 行缩减至 ~40 行；`rag/preprocess.py` 从 ~150 行（parser 类）缩减至 ~50 行。合计减少 ~170 行状态机代码 |
| **可靠性提升** | `BeautifulSoup` 处理残缺/不规范 HTML 的能力远强于手写状态机（自动补全未闭合标签、处理嵌套异常） |
| **可维护性** | HTML 结构变更时，用 CSS selector（如 `div[role="main"]`）调整即可，无需重审状态机 |
| **测试减负** | 无需测试手写状态机的 edge case（未闭合标签、嵌套异常），只需验证业务行为（噪音移除、章节提取） |

### 负面影响 / 风险

| 风险 | 说明 | 缓解措施 |
|------|------|---------|
| 供应链面扩大 | 新增一个第三方依赖 | `beautifulsoup4` 为成熟库（GitHub 10k+ stars），纯 Python，无 native 扩展，审计成本低 |
| 解析行为差异 | `BeautifulSoup` 的容错补全可能产生与 `HTMLParser` 不同的文本结构 | 所有现有单元测试保留作为回归保护；输出格式（纯文本 / section 列表）不变，仅内部解析路径变更 |
| P5 约束放宽 | 生产依赖从 3 个增至 4 个 | 本 ADR 本身即为批准记录；`beautifulsoup4` 被明确纳入已批准依赖白名单 |
| 性能 | `BeautifulSoup` 比 `HTMLParser` 慢（构建 DOM 树） | 单次 HTML 文档大小通常 < 500KB，解析耗时在可接受范围（< 100ms）；非热路径 |

## 替代方案

### 替代方案 A：继续维护手写 HTMLParser

保留现有两套 `HTMLParser` 实现，针对新发现的 edge case 继续打补丁。

**否决理由**：边际收益递减。`HTMLParser` 状态机已证明对复杂嵌套 HTML（GDAL Sphinx 生成文档）不可靠，继续维护的投入已超过引入一个成熟库的代价。

### 替代方案 B：使用 `lxml`

引入 `lxml` 替代 `BeautifulSoup`。`lxml` 基于 C 扩展，解析速度更快。

**否决理由**：`lxml` 包含 native 扩展（libxml2），跨平台安装复杂度高（尤其在 Windows 上需要编译器或预编译 wheel）。`beautifulsoup4` 纯 Python，配合 `html.parser` 内置驱动器即可满足需求，无需 native 依赖。

## 相关文档

- `Document/spec.md` — §9.1 P5 原则（需更新以反映 beautifulsoup4 纳入白名单）
- `Document/constitution.md` — §9.1 P5 依赖列表
- `Document/plan-j2-generate.md` — DC-0088 文档提取器设计决策（需更新）
- `SourceCode/src/templates/extractors.py` — HtmlExtractor 重构
- `SourceCode/src/rag/preprocess.py` — _GDALDocParser 重构
- `SourceCode/pyproject.toml` — 生产依赖声明
