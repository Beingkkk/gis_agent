# Plan-Core 模块实现任务清单

> 基于 `plan-core.md` (DC-0040 ~ DC-0049) 和已对齐的修正版本
> 前置依赖：`templates.scanner` 已就绪（DC-0041 已落地）
> 创建日期: 2026-05-27

---

## 模块总览

Plan-Core 实现 GIS Agent 的核心业务逻辑层，包含：

| 组件 | 文件 | 职责 |
|------|------|------|
| `SessionState` + `Session` | `core/models.py` | 会话状态枚举与不可变上下文 |
| `TemplateRegistry` | `core/registry.py` | 模板注册表（内存索引） |
| `ParamValidator` | `core/validator.py` | 参数校验器链 |
| `SessionProcessor` | `core/processor.py` | 会话状态机处理器 |

**依赖关系**：
```
SessionProcessor → TemplateRegistry, ParamValidator, LLMClient
ParamValidator → Workspace
TemplateRegistry → (纯内存，无外部依赖)
Session → (纯数据，无外部依赖)
```

---

## T-CORE-01: SessionState + Session 数据模型

**设计依据**: plan-core §3.1 (DC-0040, DC-0043)

### 红 — 编写测试

- [ ] `tests/unit/test_session.py`:
  - `test_session_state_enum_values`: `IDLE`, `INTENT_CONFIRM`, `PARAM_COLLECT`, `SCRIPT_PREVIEW`, `EXECUTING` 5 个状态
  - `test_session_defaults`: 默认 `state=IDLE`, 空 history, template=None, 空 params, 空 candidates
  - `test_session_immutable`: frozen dataclass，创建后不能修改属性
  - `test_with_state_returns_new_instance`: `with_state()` 返回新 Session，原实例不变
  - `test_with_template`: 设置 template 后新实例正确，原实例 template 仍为 None
  - `test_with_param`: 添加参数后 params 字典正确累积
  - `test_with_history`: 追加消息后 history 列表正确
  - `test_with_param_preserves_other_fields`: 更新 param 不影响其他字段

### 绿 — 实现代码

- [ ] `core/models.py` 中追加：
  - `SessionState(Enum)` 定义 5 个状态
  - `Session(frozen dataclass)` 定义字段 + `with_state`, `with_template`, `with_param`, `with_history` 方法
  - 导入 `from llm.models import Message` 用于 history 类型

### 重构

- [ ] 确认 `core/__init__.py` 暴露 `SessionState`, `Session`
- [ ] 确认与现有 `ParamDef`/`TemplateDef` 风格一致

**涉及文件**: `core/models.py`, `core/__init__.py`, `tests/unit/test_session.py`

---

## T-CORE-02: TemplateRegistry

**设计依据**: plan-core §3.2 (DC-0041, 已对齐为"接收扫描结果")

### 红 — 编写测试

- [ ] `tests/unit/test_registry.py`:
  - `test_init_from_list`: 从 `List[TemplateDef]` 构建
  - `test_get_template_by_id`: 按 ID 查询返回正确 TemplateDef
  - `test_get_template_not_found`: 不存在 ID 返回 `None`
  - `test_list_templates`: 返回所有模板（按 ID 排序）
  - `test_get_available_ids`: 返回所有 ID 列表（用于意图分类 prompt）
  - `test_get_param_schema`: 返回指定模板的参数定义列表
  - `test_get_template_path`: 返回 `.j2` 文件的绝对路径（基于 template_dir 解析）
  - `test_empty_registry`: 空列表构建，查询均返回 None/[]

### 绿 — 实现代码

- [ ] `core/registry.py`:
  - `TemplateRegistry` 类，构造函数接收 `List[TemplateDef]`
  - 内部用 `dict[str, TemplateDef]` 索引（ID → TemplateDef）
  - `get_template()`, `list_templates()`, `get_available_ids()`, `get_param_schema()`, `get_template_path()`

### 重构

- [ ] `core/__init__.py` 暴露 `TemplateRegistry`
- [ ] 确认查询性能（字典索引 O(1)）

**涉及文件**: `core/registry.py`, `core/__init__.py`, `tests/unit/test_registry.py`

---

## T-CORE-03: ParamValidator 校验器链

**设计依据**: plan-core §3.3 (DC-0042, 已对齐：workspace 不是安全边界)

### 红 — 编写测试

- [ ] `tests/unit/test_validator.py`:
  - `test_validate_file_path_format_ok`: 正常相对路径通过
  - `test_validate_file_path_empty`: 空字符串失败
  - `test_validate_file_path_must_exist_missing`: must_exist=True 但文件不存在 → `PathNotFoundError`
  - `test_validate_file_path_must_exist_present`: must_exist=True 且文件存在 → 通过
  - `test_validate_crs_epsg_ok`: `EPSG:4326` 格式通过
  - `test_validate_crs_invalid`: `INVALID` 格式失败
  - `test_validate_string_ok`: 普通字符串通过
  - `test_validate_string_empty`: 空字符串失败
  - `test_validate_boolean_true_values`: `yes`, `true`, `1` → True
  - `test_validate_boolean_false_values`: `no`, `false`, `0` → False
  - `test_validate_boolean_invalid`: `maybe` → 失败
  - `test_validate_all_required_missing`: 必填参数缺失 → 错误列表含该参数
  - `test_validate_all_optional_with_default`: 可选参数未提供 → 自动填充默认值
  - `test_validate_all_returns_converted_values`: 校验通过后返回转换后的参数值（如 boolean 转为 bool 类型）

### 绿 — 实现代码

- [ ] `core/validator.py`:
  - `ValidationResult = tuple[bool, Optional[str]]` 类型别名
  - `ParamValidator` 类，构造函数接收 `Workspace`
  - `validate(param_def, value)`：根据 param_def.type 分发到具体校验器
  - `validate_all(template, params)`：批量校验 + 默认值填充
  - 各类型校验器函数：`_validate_file_path`, `_validate_crs`, `_validate_string`, `_validate_boolean`

### 重构

- [ ] `core/__init__.py` 暴露 `ParamValidator`, `ValidationResult`
- [ ] 确认 `file_path` 类型不再检查"是否在工作空间内"，只做 must_exist 和格式检查

**涉及文件**: `core/validator.py`, `core/__init__.py`, `tests/unit/test_validator.py`

---

## T-CORE-04: SessionProcessor 状态机

**设计依据**: plan-core §3.4, §3.5 (DC-0040, DC-0043, DC-0044, 已对齐：SCRIPT_PREVIEW 不处理 Y/N)

### 红 — 编写测试

- [ ] `tests/unit/test_processor.py`:

**IDLE 状态**:  
  - `test_idle_high_confidence_goes_to_param_collect`: 置信度 >= 0.7 → PARAM_COLLECT，模板已设置
  - `test_idle_low_confidence_goes_to_intent_confirm`: 置信度 < 0.7 → INTENT_CONFIRM，candidates 含候选项
  - `test_idle_no_match_stays_idle`: 无匹配模板 → IDLE，提示无法识别

**INTENT_CONFIRM 状态**:  
  - `test_intent_confirm_selection_goes_to_param_collect`: 用户选择候选 → PARAM_COLLECT
  - `test_intent_confirm_deny_goes_to_idle`: 用户否认 → IDLE，提示重新描述

**PARAM_COLLECT 状态**:  
  - `test_param_collect_incomplete_stays_collect`: 参数缺失 → PARAM_COLLECT，追问缺失字段
  - `test_param_collect_complete_goes_to_preview`: 参数完整 → SCRIPT_PREVIEW，展示脚本
  - `test_param_collect_validation_failed_stays_collect`: 校验失败 → PARAM_COLLECT，提示具体错误

**SCRIPT_PREVIEW 状态**:  
  - `test_script_preview_returns_script_text`: 返回渲染后的脚本文本（不处理 Y/N）
  - `test_script_preview_render_error_goes_back`: 渲染失败 → PARAM_COLLECT，返回错误提示

**会话不可变性**:  
  - `test_process_returns_new_session`: 每次 process 返回新 Session 实例

**无效状态**:  
  - `test_invalid_state_raises_value_error`: 未知状态抛 `ValueError`

### Mock 策略（测试中使用）

- `LLMClient.chat()` mock：返回预设的 JSON 响应（用于 `classify_intent` / `extract_params`）
- `TemplateRegistry`：内存中的测试注册表（2-3 个模板）
- `ParamValidator`：使用真实 Workspace（临时目录）
- `TemplateEngine.render()` mock：返回预设的 RenderedScript

### 绿 — 实现代码

- [ ] `core/processor.py`:
  - `SessionProcessor` 类，构造函数注入依赖：`TemplateRegistry`, `ParamValidator`, `LLMClient`, `PromptBuilder`
  - `process(session, user_input)` → `(Session, str)`：主分发方法
  - `_handle_idle()`, `_handle_intent_confirm()`, `_handle_param_collect()`, `_handle_script_preview()`：各状态处理
  - 内部调用 `classify_intent()` / `extract_params()`（来自 `llm/` 模块）
  - `_build_script_preview()`：调用 `TemplateEngine.render()` 生成脚本

### 重构

- [ ] `core/__init__.py` 暴露 `SessionProcessor`
- [ ] 确认状态转换显式可追溯
- [ ] 确认所有 LLM 调用通过 `llm/` 模块（CODE-3 合规）

**涉及文件**: `core/processor.py`, `core/__init__.py`, `tests/unit/test_processor.py`

---

## 编码顺序

```
T-CORE-01 (Session) → T-CORE-02 (Registry) → T-CORE-03 (Validator) → T-CORE-04 (Processor)
```

**原因**：Processor 依赖 Registry、Validator、Session；Validator 依赖 Workspace；Registry 和 Session 是纯数据模型，无外部依赖。必须按依赖顺序编码。

---

## 质量门禁（每步完成后执行）

- [ ] `ruff format src/ tests/`
- [ ] `ruff check src/ tests/`
- [ ] `mypy --strict src/`
- [ ] `pytest tests/unit/ -v`
- [ ] 覆盖率 ≥ 80%

---

## 需求追溯

| 需求 ID | 设计决策 | 任务 | 说明 |
|:-------:|:--------:|:----:|------|
| F2 | DC-0040, DC-0044 | T-CORE-04 | 意图分类与澄清 |
| F3 | DC-0040, DC-0042 | T-CORE-03, T-CORE-04 | 参数抽取与校验 |
| F8 | DC-0043 | T-CORE-01 | 会话上下文不可变快照 |
| P1 | DC-0041 | T-CORE-02 | 模板化命令映射 |
| P2 | DC-0040 | T-CORE-04 | SCRIPT_PREVIEW 先展后行 |
| CODE-2 | DC-0042 | T-CORE-03 | 路径规范化 + must_exist |
| CODE-3 | DC-0031 | T-CORE-04 | LLM 调用封装在 llm/ |
| CODE-5 | — | 全部 | 异常不静默吞没 |
