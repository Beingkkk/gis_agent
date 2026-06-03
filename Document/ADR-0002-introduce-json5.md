# ADR-0002: 引入 `json5` 作为 LLM JSON 输出容错解析依赖

## 状态

- 已通过

## 上下文

模板生成器（`llm/template_generator.py`）负责将 LLM 的文本输出解析为结构化 JSON。LLM（尤其是 Claude）在生成长文本 JSON 时频繁出现以下格式错误：

1. **未转义换行符**：字符串值内部出现原始 `\n`/`\r`（如多行 description）
2. **无效转义序列**：Windows 路径中的 `\U`、`\d` 等被当作 Unicode 转义
3. **未转义双引号**：字符串值内部出现英文双引号 `"`（如引用参数名）
4. **裸键**：`{name: "value"}` 省略键引号
5. **尾随逗号**：`{"a": 1,}` 末尾多余逗号
6. **单引号字符串**：`{'id': 'test'}` 使用单引号

此前采用自研修复逻辑（~150 行），通过 `_fix_json_keys`、`_fix_json_string_issues`、`_fix_json_invalid_escapes`、`_remove_trailing_commas`、`_fix_unescaped_quotes_by_error`、`_try_parse_with_ast` 等函数逐层容错。实践中暴露出以下问题：

- **维护成本高**：每发现一种新的 LLM JSON 错误模式，需要新增一个修复函数 + 测试
- **修复不彻底**：未转义双引号的回溯修复依赖启发式，单引号与双引号混用时容易误判键引号为值内部引号
- **代码膨胀**：解析逻辑已占 `template_generator.py` 近 40% 行数，与模板生成的核心职责偏离

## 决策

1. **引入 `json5` 作为生产依赖**。`json5` 是 JSON 的超集，原生支持：
   - 裸键（`{name: "value"}`）
   - 单引号字符串（`{'id': 'test'}`）
   - 尾随逗号（`{"a": 1,}`）
   - 注释（`//` 和 `/* */`）
   - 多行字符串（未转义换行符自动处理）

   以上恰好覆盖 LLM 输出的 90%+ 破损模式。引入后可删除大部分自研修复逻辑。

2. **保留双层 fallback 结构**：
   - **第一层**：`json5.loads()` — 处理宽松 JSON
   - **第二层**：自研轻量修复（仅保留 markdown fence 剥离 + 裸键修复 + `{...}` 块提取）— 处理 json5 也无法覆盖的极端情况
   - **第三层**：`ast.literal_eval()` — 处理 Python 风格字面量

3. **保留 `generate_template_stream` 的重试逻辑**。解析器增强不替代 LLM 重试，两者互补：解析器容错处理偶发格式错误，重试处理 LLM 输出完全偏离 JSON 的情况。

## 后果

### 正面影响

| 方面 | 说明 |
|------|------|
| **代码简化** | `template_generator.py` 解析相关代码从 ~200 行缩减至 ~50 行，删除 `_fix_json_string_issues`、`_fix_json_invalid_escapes`、`_remove_trailing_commas`、`_fix_unescaped_quotes_by_error`、`_try_parse_with_ast` 五个函数 |
| **容错增强** | `json5` 对未转义换行、单引号、尾随逗号的处理比自研逻辑更可靠 |
| **维护减负** | 未来发现新的 JSON 破损模式时，优先评估 `json5` 是否已覆盖；极少需要新增自研修复 |
| **行为一致** | `json5` 有明确的规范文档，修复行为可预期；自研启发式的行为边界难以穷尽 |

### 负面影响 / 风险

| 风险 | 说明 | 缓解措施 |
|------|------|---------|
| 供应链面扩大 | 新增一个第三方依赖，增加依赖审查和维护面 | `json5` 为成熟库（GitHub 6k+ stars），无 native 扩展，纯 Python，审计成本低 |
| 解析行为差异 | `json5` 的宽松规则可能接受某些"几乎但不是 JSON"的边界文本，而 `json.loads` 会拒绝 | 这是期望行为（容错增强）；对安全性敏感的场景（如模板参数注入）已在 `ScriptSecurityChecker` 层处理 |
| P5 约束放宽 | 生产依赖从 2 个增至 3 个 | 本 ADR 本身即为批准记录；`json5` 被明确纳入已批准依赖白名单 |

## 替代方案

### 替代方案 A：继续扩展自研修复逻辑

保留现有策略，针对新发现的错误模式继续堆叠修复函数。

**否决理由**：边际收益递减。当前已覆盖最常见模式，继续扩展会面临复杂的组合爆炸（换行 + 引号 + 转义 + 单引号混用）。自研代码行数已超过引入一个成熟库的代价。

### 替代方案 B：使用 `demjson3` 或 `json-repair`

引入专门修复破损 JSON 的库。

**否决理由**：`demjson3` 功能过重（还包含编码器），`json-repair` 相对较新。`json5` 作为 JSON 超集规范，语义更清晰，社区更成熟。

## 相关文档

- `Document/spec.md` — §4.1 依赖栈、§9.1 P5 原则（需更新以反映 json5 纳入白名单）
- `Document/constitution.md` — §6.2 依赖规则、§8.2 质量门禁依赖检查项
- `Document/plan-j2-generate.md` — DC-0094 共享生成引擎（需更新解析策略描述）
- `SourceCode/src/llm/template_generator.py` — 解析逻辑重构
- `SourceCode/pyproject.toml` — 生产依赖声明
