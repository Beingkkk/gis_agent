# plan-core

| 项目 | 内容 |
|------|------|
| 版本 | v1.0.8 |
| 状态 | 设计基线 |
| 作者 | - |
| 日期 | 2026-06-02 |

---

## 1. 设计概述

### 1.1 模块职责

实现 GIS Agent 的核心业务逻辑：交互状态机、模板注册表管理、参数校验链、会话上下文维护。本模块是**CLI 层与 LLM/rag 层之间的协调中枢**，将 LLM 的"意图分类"和"参数抽取"能力转化为结构化的任务描述，供模板引擎消费。

### 1.2 所属架构层次

核心层（`core/`）。可依赖 llm 层和 rag 层，被 CLI 层依赖。

### 1.3 对应需求项

| 需求 ID | 需求描述 |
|:-------:|---------|
| F2 | 意图→模板映射：自然语言分类到预定义工作流模板 |
| F3 | 参数抽取与追问：提取文件路径、坐标参考、选项等 |
| F8 | 会话内记忆：单次对话中保留上下文 |
| F9 | 多步任务（预留）：链式操作支持 |
| P1 | 模板化命令，杜绝幻觉 |
| P2 | 先展后行 |

---

## 2. 设计决策

### DC-0040: 状态机采用 Enum + 主循环分发

**决策**: 定义 `SessionState` Enum 表示各交互阶段，主循环通过 `if/elif` 根据当前状态分发处理逻辑。

**理由**:
- 当前状态数量少（空闲、意图确认、参数收集、脚本展示、执行），不需要复杂的状态模式
- Python Enum 类型安全，状态转换显式可追溯
- 简单直接，调试友好

**预留扩展**: F9 多步任务链可扩展为"任务栈"结构，在现有状态机上叠加任务队列，不改变基础架构。

**状态定义**:
```
IDLE ──→ 用户输入自然语言
   │
   ▼
INTENT_CONFIRM ──→ 用户确认/否认意图
   │
   ▼
PARAM_COLLECT ──→ 参数完整？
   │     │
   │否   │是
   │     ▼
   └──→ 追问缺失参数
   │
   ▼
SCRIPT_PREVIEW ──→ 用户确认 Y/N
   │
   ├──→ Y ──→ EXECUTING
   │             │
   │             ├──→ 成功 ──→ 返回 IDLE
   │             │
   │             └──→ 失败 ──→ ERROR_RECOVERY ──→ 用户选择修复路径
   │                                                  │
   │                    ┌──→ 确认修正 ──→ SCRIPT_PREVIEW
   │                    │
   │                    ├──→ 手动修改 ──→ PARAM_COLLECT
   │                    │
   │                    └──→ 放弃 ──→ IDLE
   │
   └──→ N ──→ 返回 PARAM_COLLECT（修改参数）
```

### DC-0041: 模板注册表采用 Jinja2 注释头 + 启动扫描

**决策**: 模板元数据内联在每个 `.j2` 文件的 Jinja2 注释头中。Agent 启动时递归扫描 `SourceCode/data/templates/`，解析注释提取 `id`、`name`、`description` 和 `params`，构建内存注册表。

**注释格式**:
```jinja2
{# @id shp2geojson #}
{# @name Shapefile 转 GeoJSON #}
{# @description 将 Shapefile 格式转换为 GeoJSON #}
{# @param input file_path required 输入 Shapefile 路径 #}
{# @param t_srs crs optional 目标坐标系 default=EPSG:4326 #}
```

**理由**:
- 一个文件 = 模板体 + 元数据，消除 JSON 注册表与 `.j2` 的同步负担
- 新增模板只需创建单个 `.j2` 文件，无需编辑 JSON
- Jinja2 注释天然适合承载元数据，不干扰模板渲染
- 扫描开销低（只读前 50 行），模板数量通常 < 100

**替代方案**:
- JSON 注册表（已否决）：文件分离导致维护负担，用户扩展时需同时编辑两个文件

**扫描器 API**:
```python
def scan_templates(template_dir: Path) -> List[TemplateDef]:
    """递归扫描 .j2 文件，解析注释头构建注册表。"""
```

### DC-0042: 参数校验采用"校验器链"模式

**决策**: 每个参数类型对应一个校验器函数，按顺序执行：类型转换 → 格式校验 → 业务规则校验 → 路径安全校验。

**理由**:
- 避免单个巨型校验函数
- 校验器可复用（`file_path` 校验器被多个模板共享）
- 新增参数类型只需添加校验器，不改动现有代码

**参数类型与校验器映射**:

| 参数类型 | 校验内容 | 校验器 |
|---------|---------|--------|
| `file_path` | 非空、must_exist 时校验文件系统存在性 | `validate_file_path` |
| `crs` | EPSG 格式（`EPSG:\d+`）或 WKT 字符串 | `validate_crs` |
| `format` | 在 GDAL 支持的格式列表中 | `validate_format` |
| `string` | 非空、无特殊字符 | `validate_string` |
| `integer` | 可解析为整数、在范围内（如有） | `validate_integer` |
| `boolean` | 解析为布尔值（yes/no/true/false/1/0） | `validate_boolean` |

### DC-0043: 会话上下文以不可变快照形式维护

**决策**: `Session` 对象维护当前状态、对话历史、已选模板、已收集参数。每次状态转换生成新的 Session 实例（函数式更新），便于调试和回溯。

**理由**:
- 不可变对象避免副作用，状态变更显式
- 便于实现 `/undo` 等扩展功能（保留历史 Session 快照）
- 测试时可直接构造任意状态的 Session

**替代方案**: 可变对象（直接修改属性）。更省内存，但调试困难，状态变更不可追溯。

### DC-0044: 意图置信度低于阈值时进入澄清状态

**决策**: 当 LLM 返回的 `confidence < 0.7` 时，不直接进入参数收集，而是向用户列出最可能的 2-3 个模板选项，要求用户确认。

**理由**:
- 避免 LLM 误判意图导致生成错误脚本
- 给用户选择权，提升可控感
- 0.7 阈值可根据实际效果调整（放入 Config）

**更新（DC-0098）**：两阶段匹配机制上线后，低置信度分支的行为被细化：
- 关键词粗筛得分 ≥ 8（约命中 2-3 个 keywords）时直接 PARAM_COLLECT，无需 LLM
- 否则进入 LLM 精排；精排结果按 confidence 分三级处理（见 DC-0098）

### DC-0048: 新增 ERROR_RECOVERY 状态用于执行失败后的上下文保留

**决策**: 在 `SessionState` 中新增 `ERROR_RECOVERY` 状态。脚本执行失败后进入该状态，保留 `template` 和 `params` 上下文，不直接返回 `IDLE`。

**理由**:
- 执行失败后用户最常见的操作是修改参数重试，返回 IDLE 会丢失全部上下文
- 保留 template + params 让用户可以直接说"把 input 改成 xxx"而不必重新描述需求
- 状态机职责统一：错误恢复逻辑由 processor 处理，REPL 只负责驱动执行和切换状态

**与其他状态的区别**:
| 状态 | 保留 context | 用户输入语义 |
|------|-------------|-------------|
| PARAM_COLLECT | template + params | 补充/修改参数 |
| ERROR_RECOVERY | template + params + error_context | 选择修复路径或修改参数 |
| IDLE | 无 | 全新需求 |

### DC-0049: 错误恢复由 `_handle_error_recovery` 统一处理

**决策**: `SessionProcessor` 新增 `_handle_error_recovery()` handler，统一处理执行失败后的用户交互：首次进入触发 LLM 诊断，后续进入解析用户选择。

**处理逻辑**:
1. **首次进入**（`error_context.diagnosis is None`）：调用 `analyze_execution_error()` 获取诊断，生成选项菜单，保持在 `ERROR_RECOVERY`
2. **用户选"确认修正"**（`can_auto_fix=True` 时）：应用 `fixed_params` → `SCRIPT_PREVIEW`
3. **用户选"手动修改"**：清除 `error_context` → `PARAM_COLLECT`
4. **用户选"放弃"**：清除 `error_context` + `template` + `params` → `IDLE`
5. **用户输入非选项内容**：当作参数修改语句 → `PARAM_COLLECT`

**理由**:
- 状态机集中管理所有状态流转，REPL 不分散错误恢复逻辑
- LLM 诊断只需在首次进入时调用一次，结果缓存到 `error_context.diagnosis`
- 用户输入语义分层：选项选择（1/2/3）vs 自然语言修改语句

### DC-0070: SessionProcessor 支持可选 `output_fn` 回调用于 Q&A 流式输出

**决策**: `SessionProcessor.__init__()` 新增 `output_fn: Optional[Callable[[str], None]] = None` 参数，并新增 `set_output_fn()` 后置设置方法。Q&A 路由（`_handle_idle` 中的 `__qa__` 分支）将该 callback 作为 `on_chunk` 传给 `answer_question()`。

**理由**:
- Processor 拥有"哪些响应应该流式"的决策权（仅 Q&A 流式，结构化调用不流式）
- 可选注入，不注入时流式功能静默禁用（向后兼容）
- 不直接依赖 CLI 层，只是一个 callable 类型的可选参数

### DC-0091: 扩展参数类型系统支持 enum、format、text、float、folder_path

**决策**: `ParamDef` 新增 `options: List[str]` 字段，`type` 域扩展为支持 `enum`、`format`、`text`、`float`、`folder_path` 五种新类型。

**类型语义**:

| 类型 | 用途 | 前端渲染 | 校验规则 |
|------|------|---------|---------|
| `enum` | 通用枚举，选项由模板作者定义 | select 下拉框 | 值必须在 options 列表中 |
| `format` | GDAL 输出格式专用枚举 | select 下拉框 | 值必须在 options 列表中 |
| `text` | 多行文本（与 string 语义相同） | textarea | 非空校验（同 string） |
| `float` | 浮点数 | number input (step=any) | 可解析为 float |
| `folder_path` | 目录路径 | text + 浏览按钮 | 非空，must_exist 时校验目录存在性 |

**理由**:
- `of`（输出格式）等参数用 `string` 类型导致前端只能渲染为文本框，用户不知道合法取值
- `format` 与 `enum` 共用校验逻辑但语义不同，便于前端做差异化处理
- `folder_path` 与 `file_path` UI 相同但语义不同，便于前端未来扩展为目录选择器

**向后兼容**: 旧模板无 `options` 字段时默认为空列表；未知类型回退到 `string` 校验。

### DC-0093: 新增五种参数类型的校验器

**决策**: `ParamValidator` 新增 `_validate_folder_path`、`_validate_float`、`_validate_enum` 三个校验方法，`text` 复用 `_validate_string`。

**校验器映射**:

| 类型 | 校验器方法 |
|------|-----------|
| `folder_path` | `_validate_folder_path` |
| `float` | `_validate_float` |
| `enum` | `_validate_enum` |
| `format` | `_validate_enum`（复用） |
| `text` | `_validate_string`（复用） |

**理由**: 校验器链模式（DC-0042）天然支持扩展；`enum` 与 `format` 共用校验逻辑，减少重复代码。

### DC-0094: 提取统一的模板匹配评分函数

**决策**: 将分散在 `processor.py` 和 `api/routes/session.py` 中的模板评分逻辑提取到独立的 `core/matching.py` 模块，提供 `score_template_match()` 和 `find_matching_templates()` 两个纯函数。

### DC-0095: TemplateRegistry 支持运行时重扫描（热加载）

**决策**: `TemplateRegistry` 新增 `rescan()` 方法，在运行时重新扫描模板目录、重建内存索引，无需重启进程即可使新模板生效。`api/dependencies.py` 同步新增 `refresh_registry()` 更新全局单例引用。

**理由**:
- J2 模板生成器（plan-j2-generate DC-0093）保存新模板后，需要立即可用于意图匹配和参数收集
- 重启整个 API 进程代价过高，且会中断所有活跃会话
- 扫描开销低（只读前 50 行，模板数通常 < 100），运行时重扫无性能问题
- 单例引用更新通过依赖注入层统一管理，API 路由代码无需改动

**实现要点**:
1. `TemplateRegistry.rescan()` → 重新调用 `scan_templates(self._template_dir)`，用新结果替换 `_registry`
2. `api/dependencies.refresh_registry()` → 重新扫描并调用 `set_registry(new_registry)`
3. 线程安全：Python dict 操作原子性（GIL），`rescan()` 整体为原子替换，读取方不会看到半完成状态

**依赖关系**:
- plan-j2-generate DC-0093（保存后自动热加载）依赖本决策
- plan-templates DC-0050（按子目录分类）已由 `rglob("*.j2")` 天然支持

**评分权重**:

| 匹配源 | 权重 | 说明 |
|--------|------|------|
| keywords | +3 | 人工精选的匹配词，权重最高 |
| concepts | +2 | 知识元数据，质量较高 |
| id/name/description | +1 | 基础元数据 |
| notes | +1 | 补充说明 |

**理由**:
- 消除代码重复（processor.py 和 API 路由三处评分逻辑）
- 评分规则集中管理，便于调优
- 纯函数便于单元测试

### DC-0098: 两阶段匹配（关键词粗筛 + LLM 精排）+ 自动决策

**决策**: API 层和 CLI 层的意图匹配统一采用两阶段流程：

1. **Phase 0（统一打分）**：对 ALL 模板执行 `score_template_match()`（代码层关键词匹配，O(n)，毫秒级）。
2. **Phase 1（快速路径）**：最高分 ≥ 8（约命中 2-3 个 keywords）→ 直接 `PARAM_COLLECT`，跳过 LLM。
3. **Phase 2（粗筛）**：取得分前 `_CANDIDATE_POOL_SIZE=10` 的模板作为候选池。
4. **Phase 3（精排）**：调用 `classify_intent()`，仅将候选池（而非全部模板）传入 LLM，让 LLM 做语义级最佳匹配判断。
5. **Phase 4（自动决策）**：
   - `confidence ≥ 0.85`：绝对优势 → `PARAM_COLLECT`（自动选中，无需用户确认）
   - `confidence ≥ 0.50`：较强匹配 → `INTENT_CONFIRM`（仅返回 top-1 推荐 + 2 个备选）
   - `confidence < 0.50`：弱匹配 → `INTENT_CONFIRM`（返回 top-3 关键词候选）

**理由**:
- **解决 keyword 误匹配**：旧 Route 1 的 "第一个匹配就选中" 逻辑（`for template in registry.list_templates()`）导致 `shp` 可能误匹配到非转换类模板；统一打分后取最高分，消除了遍历顺序的副作用
- **缩小 LLM 上下文**：将全部 100+ 模板塞给 LLM 导致 prompt 过长、context 浪费；仅传入 top-10 候选，LLM 聚焦判断
- **语义级匹配**：用户输入 "shp转geojson" 时，关键词可能同时命中多个模板；LLM 能理解 "转" = "格式转换"，从而选出正确的 `gdal_vector_convert`/`ogr2ogr_convert`
- **自动决策减少用户操作**：当 LLM 判断某个模板绝对优势时（如候选池中只有一个是格式转换类），直接锁定，省去用户点击确认的步骤

**与 DC-0044 的关系**：DC-0044 定义了单一阈值（0.7）的澄清机制；DC-0098 在此基础上扩展为"快速路径 + 三级决策"，DC-0044 的阈值仍适用于 CLI 层 `SessionProcessor._handle_idle()` 的原有逻辑（全模板 LLM 分类），API 层采用 DC-0098 的两阶段方案。

### DC-0106: 一次性 LLM 决策调用取消 history 参数

**决策**: `classify_intent()`、`extract_params()`、`analyze_execution_error()` 三个一次性决策型 LLM 调用取消 `history` 参数，改为单轮调用（`messages = [user_prompt]`）。

**理由**:
- 意图识别、参数提取、错误诊断都是一次性决策，不需要多轮上下文
- 传入 `session.history` 反而让 LLM 被无关历史干扰（如 Discovery 阶段的模板选择对话混入参数提取上下文）
- 减少每次调用的 token 消耗和上下文窗口占用
- 简化函数签名，调用方不需要关心"该传哪份历史"

**影响范围**:
- `llm/intent.py`: `classify_intent()` 移除 `history` 参数
- `llm/params.py`: `extract_params()` 移除 `history` 参数
- `llm/diagnosis.py`: `analyze_execution_error()` 移除 `history` 参数
- `api/routes/session.py`: `process_intent()`、`diagnose_execution()` 调用时不再传 `history`
- `core/processor.py`: 三个调用点同步调整

**向后兼容**: CLI 的 `extract_params` 保留功能但不再传历史；API 层的 `submit_params` 本就不调用 `extract_params`（走 `validator.validate_all`）。

### DC-0107: Session 模型增加独立的 qa_history

**决策**: `Session` 新增 `qa_history: List[Message]` 字段，专用于 QATab 多轮对话。Discovery/Exec 流程消息继续写入 `history`，QATab 消息写入 `qa_history`。

**理由**:
- 当前 Discovery 的意图匹配消息写入 `session.history`，QATab 读取同一份 history 作为上下文 → 互相污染
- 用户可能在 Discovery 说"把 shp 转 geojson"（意图匹配），然后在 QATab 问"GeoJSON 和 Shapefile 有什么区别"——后者不需要前者作为上下文
- QATab 的 `answer_question()` 需要真正的多轮历史（追问、延伸），而 Discovery 的历史是单任务流程消息
- 分离后两个 TAB 的历史策略独立：Discovery 不累积（每次输入独立匹配），QATab 累积（多轮对话）

**接口变更**:
- `Session` 新增字段：`qa_history: List[Message] = field(default_factory=list)`
- 新增方法：`with_qa_history(message: Message) -> Session`

**与 DC-UX-15 的关系**：前端 `QATab` 通过 WebSocket Q&A 获取 LLM 回复，回复完成后后端将消息写入 `qa_history`（见 DC-UX-14）；前端 `useSession` 的 `qaMessages` 仅维护前端本地状态，不依赖后端 `history`。

---

## 3. 接口定义

### 3.1 数据模型

```python
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional

from llm import Message
from llm.models import ErrorDiagnosis  # forward ref for type hint


@dataclass(frozen=True)
class ExecutionErrorContext:
    """执行错误的上下文信息，附加在 Session 上供 ERROR_RECOVERY 使用。

    Design:
        DC-0048
    """
    returncode: int
    stdout: str
    stderr: str
    duration_ms: int
    diagnosis: Optional[ErrorDiagnosis] = None  # LLM 诊断结果（首次处理后填充）


class SessionState(Enum):
    """会话状态。"""
    IDLE = auto()              # 空闲，等待用户输入
    INTENT_CONFIRM = auto()    # 意图待确认（低置信度时）
    PARAM_COLLECT = auto()     # 参数收集中
    SCRIPT_PREVIEW = auto()    # 脚本展示，等待用户确认
    EXECUTING = auto()         # 脚本执行中
    ERROR_RECOVERY = auto()    # 执行失败后的恢复状态（DC-0048）


@dataclass(frozen=True)
class ParamDef:
    """参数定义（来自模板注册表）。"""
    name: str
    type: str
    required: bool
    description: str
    default: Optional[str] = None


@dataclass(frozen=True)
class TemplateDef:
    """模板定义（来自模板注册表）。"""
    id: str
    name: str
    description: str
    template_file: str
    params: List[ParamDef]


@dataclass(frozen=True)
class Session:
    """会话上下文。"""
    state: SessionState = SessionState.IDLE
    history: List[Message] = field(default_factory=list)     # Discovery/Exec 流程消息
    qa_history: List[Message] = field(default_factory=list)  # QATab 多轮对话（DC-0107）
    template: Optional[TemplateDef] = None
    params: Dict[str, str] = field(default_factory=dict)
    candidates: List[TemplateDef] = field(default_factory=list)  # 澄清候选项
    error_context: Optional[ExecutionErrorContext] = None  # DC-0048

    def with_state(self, state: SessionState) -> "Session":
        """返回状态变更后的新 Session。"""

    def with_template(self, template: Optional[TemplateDef]) -> "Session":
        """返回选定模板后的新 Session（传 None 表示清空模板）。"""

    def with_param(self, name: str, value: str) -> "Session":
        """返回添加参数后的新 Session。"""

    def with_history(self, message: Message) -> "Session":
        """返回追加消息后的新 Session（Discovery/Exec 流程）。"""

    def with_qa_history(self, message: Message) -> "Session":
        """返回追加 QA 消息后的新 Session（QATab 专属，DC-0107）。"""

    def with_candidates(self, candidates: List[TemplateDef]) -> "Session":
        """返回更新澄清候选项后的新 Session。"""

    def with_error(self, error_context: Optional[ExecutionErrorContext]) -> "Session":
        """附加/更新错误上下文。"""

    def clear_error(self) -> "Session":
        """清除错误上下文（恢复成功或放弃任务时）。"""
```

### 3.2 模板注册表

```python
class TemplateRegistry:
    """模板注册表。

    接收 ``templates.scanner.scan_templates()`` 的扫描结果构建，提供模板查询和参数 Schema 访问。进程内单例。

    Design:
        DC-0041
    """

    def __init__(self, templates: List[TemplateDef]) -> None:
        """从扫描结果构建注册表。

        Args:
            templates: 扫描得到的 TemplateDef 列表（由 ``scan_templates`` 产出）。
        """

    def get_template(self, template_id: str) -> Optional[TemplateDef]:
        """按 ID 获取模板定义。"""

    def list_templates(self) -> List[TemplateDef]:
        """获取所有模板列表。"""

    def get_available_ids(self) -> List[str]:
        """获取所有模板 ID 列表（用于意图分类）。"""

    def get_param_schema(self, template_id: str) -> List[ParamDef]:
        """获取指定模板的参数定义列表。"""

    def get_template_path(self, template_id: str) -> Path:
        """获取模板 .j2 文件的绝对路径。"""

    def rescan(self) -> int:
        """运行时重新扫描模板目录，重建内存索引。

        重新调用 ``scan_templates(self._template_dir)``，用新扫描结果
        替换内部 ``_registry``。返回新发现的模板数量。

        Returns:
            本次重扫描后注册表中的模板总数。

        Design:
            DC-0095
        """
```

### 3.3 参数校验器

```python
from typing import Callable, Optional


ValidationResult = tuple[bool, Optional[str]]
# (is_valid, error_message)


class ParamValidator:
    """参数校验器链。

    Design:
        DC-0042
    """

    def __init__(self, workspace: Workspace) -> None:
        """Args:
            workspace: 用于 file_path 类型的路径存在性校验（must_exist）。
                Workspace v2.0 是记忆锚点，不是安全边界；绝对路径直接放行。
        """

    def validate(self, param_def: ParamDef, value: str) -> ValidationResult:
        """对单个参数值执行完整校验链。

        Args:
            param_def: 参数定义（含类型、必填、约束）。
            value: 用户提供的值。

        Returns:
            (True, None) 表示校验通过。
            (False, error_msg) 表示校验失败，error_msg 可直接展示给用户。
        """

    def validate_all(
        self,
        template: TemplateDef,
        params: Dict[str, str],
    ) -> tuple[Dict[str, str], List[str]]:
        """批量校验模板的所有参数。

        Returns:
            (valid_params, error_messages)
            valid_params: 校验通过的参数（含默认值填充）。
            error_messages: 校验失败的错误信息列表。
        """
```

### 3.4 会话处理器

```python
class SessionProcessor:
    """会话状态处理器。

    封装状态机逻辑，将用户输入转化为状态转换和响应。

    Design:
        DC-0040, DC-0043, DC-0044
    """

    def __init__(
        self,
        registry: TemplateRegistry,
        validator: ParamValidator,
        llm_client: LLMClient,
        prompt_builder: PromptBuilder,
        output_fn: Optional[Callable[[str], None]] = None,
    ) -> None:
        """注入依赖。

        Args:
            output_fn: 可选的输出回调，用于 Q&A 流式输出（DC-0070）。
        """

    def set_output_fn(self, fn: Optional[Callable[[str], None]]) -> None:
        """后置设置输出回调（用于 REPL 创建后接线）。"""

    def process(self, session: Session, user_input: str) -> tuple[Session, str]:
        """处理一轮用户输入，返回新状态和响应文本。

        Args:
            session: 当前会话状态。
            user_input: 用户输入文本（空字符串表示仅刷新状态）。

        Returns:
            (new_session, response_text)
            response_text 是展示给用户的自然语言响应。

        Raises:
            ValueError: session.state 为无效状态。
        """
```

### 3.5 状态机处理逻辑

```python
def _handle_idle(
    self,
    session: Session,
    user_input: str,
) -> tuple[Session, str]:
    """空闲状态：进行意图分类。

    调用 classify_intent() 时不传 history（DC-0106），仅传入候选模板列表。

    - 高置信度（>=0.7）→ PARAM_COLLECT，展示任务名称和所需参数列表
    - 低置信度（<0.7）→ INTENT_CONFIRM，列出候选模板让用户选择
    - 无匹配（LLM 返回空 template_id）→ INTENT_CONFIRM，展示候选模板让用户选择，附带友好说明
    """


def _handle_intent_confirm(
    self,
    session: Session,
    user_input: str,
) -> tuple[Session, str]:
    """意图确认状态：用户从候选中选择或否认。

    - 用户选择模板 → PARAM_COLLECT，展示任务名称和所需参数列表
    - 用户否认 → IDLE，提示重新描述需求
    """


def _handle_param_collect(
    self,
    session: Session,
    user_input: str,
) -> tuple[Session, str]:
    """参数收集状态：抽取参数，检查完整性。

    调用 extract_params() 时不传 history（DC-0106），仅传入 param_schema 和 current_params。

    - 参数完整且校验通过 → SCRIPT_PREVIEW，展示脚本
    - 有缺失参数 → 保持在 PARAM_COLLECT，追问缺失字段
    - 校验失败 → 保持在 PARAM_COLLECT，提示具体错误
    """


def _handle_script_preview(
    self,
    session: Session,
    user_input: str,
) -> tuple[Session, str]:
    """脚本展示状态：生成脚本展示文本。

    本方法**不处理** Y/N 确认交互（由 CLI 层的 REPL 负责）。
    仅负责调用模板引擎渲染脚本，并返回展示文本。

    - 渲染成功 → 返回 (SCRIPT_PREVIEW, script_text)
    - 渲染失败 → 返回 (PARAM_COLLECT, 错误提示)
    """


def _handle_executing(
    self,
    session: Session,
    user_input: str,
) -> tuple[Session, str]:
    """执行状态：理论上不由本层处理，由 CLI 层驱动。

    执行完成后返回 IDLE。
    """


def _handle_error_recovery(
    self,
    session: Session,
    user_input: str,
) -> tuple[Session, str]:
    """错误恢复状态：LLM 诊断 + 用户选择修复路径。

    首次进入（error_context.diagnosis is None）：
        - 调用 analyze_execution_error() 获取诊断（不传 history，DC-0106）
        - 显示诊断结果 + 选项菜单
        - 保持在 ERROR_RECOVERY

    用户已看到诊断，输入选择：
        - "1"/"Y"/"确认" + can_auto_fix=True → 应用 fixed_params → SCRIPT_PREVIEW
        - "2"/"手动"/"修改" → PARAM_COLLECT（保留现有参数，清除 error_context）
        - "3"/"放弃"/"N" → IDLE（清除 template、params、error_context）
        - 其他输入 → 当作参数修改 → PARAM_COLLECT（清除 error_context）

    Design:
        DC-0048, DC-0049, DC-0106
    """
```

---

## 4. 数据流与控制流

### 4.1 完整会话流程（成功路径）

```
[IDLE]
  │
  │ 用户："把 roads.shp 转成 GeoJSON"
  ▼
_process_idle()
  │
  ├──→ classify_intent() (不传 history, DC-0106) → confidence=0.95, template_id="shp2geojson"
  │
  ├──→ Session.with_template(shp2geojson)
  │
  └──→ 返回 (PARAM_COLLECT,
              "已识别任务：Shapefile 转 GeoJSON。\n\n"
              "请输入以下参数：\n"
              "  • input（必填）：输入 SHP 路径\n"
              "  • output（必填）：输出 GeoJSON 路径\n"
              "  • t_srs（可选，默认 EPSG:4326）：目标 CRS")
  │
  ▼
[PARAM_COLLECT]
  │
  │ 用户："输出 roads_out.json"
  ▼
_process_param_collect()
  │
  ├──→ extract_params() → {output: "roads_out.json"}, missing: ["input"]
  │
  ├──→ ParamValidator.validate(output="roads_out.json")
  │       └── 通过
  │
  ├──→ Session.with_param("output", "roads_out.json")
  │
  └──→ 返回 (PARAM_COLLECT, "请输入输入文件路径（input）：")
  │
  ▼
[PARAM_COLLECT]
  │
  │ 用户："roads.shp"
  ▼
_process_param_collect()
  │
  ├──→ extract_params() → {input: "roads.shp"}, missing: []
  │
  ├──→ ParamValidator.validate(input="roads.shp", output="roads_out.json")
  │       └── input: Workspace.resolve_path("roads.shp", must_exist=True)
  │           └── 通过
  │
  ├──→ 所有参数完整，生成脚本（调用模板引擎）
  │
  └──→ 返回 (SCRIPT_PREVIEW, "脚本内容：\nogr2ogr -f GeoJSON ...\n\n确认执行？(Y/N)")
  │
  ▼
[SCRIPT_PREVIEW]
  │
  │ 用户："Y"
  ▼
_process_script_preview()
  │
  ├──→ 返回 (EXECUTING, "开始执行...")
  │
  ▼
[EXECUTING] → CLI 层执行脚本 → 成功
  │
  ▼
[IDLE]
```

### 4.2 意图澄清流程（低置信度）

```
[IDLE]
  │
  │ 用户："处理一下那个文件"
  ▼
_process_idle()
  │
  ├──→ classify_intent() (不传 history, DC-0106) → confidence=0.45, top3=[shp2geojson, merge_shp, clip_raster]
  │
  ├──→ 低于阈值 0.7，进入澄清
  │
  └──→ 返回 (INTENT_CONFIRM,
              "我无法确定您的意图，请选择：\n"
              "1. Shapefile 转 GeoJSON\n"
              "2. 合并 Shapefile\n"
              "3. 栅格裁剪\n"
              "或请重新描述您的需求")
  │
  ▼
[INTENT_CONFIRM]
  │
  │ 用户："1"
  ▼
_process_intent_confirm()
  │
  ├──→ 解析选择 → template_id="shp2geojson"
  │
  └──→ 返回 (PARAM_COLLECT,
              "已识别任务：Shapefile 转 GeoJSON。\n\n"
              "请输入以下参数：\n"
              "  • input（必填）：输入 SHP 路径\n"
              "  • output（必填）：输出 GeoJSON 路径\n"
              "  • t_srs（可选，默认 EPSG:4326）：目标 CRS")
```

### 4.3 参数校验失败流程

```
[PARAM_COLLECT]
  │
  │ 用户："input: /data/roads.shp"
  ▼
_process_param_collect()
  │
  ├──→ extract_params() (不传 history, DC-0106) → {input: "/data/roads.shp"}
  │
  ├──→ ParamValidator.validate(input="/data/roads.shp")
  │       └── Workspace.resolve_path("/data/roads.shp", must_exist=True)
  │           └── PathNotFoundError → 返回错误"文件不存在"
  │
  └──→ 返回 (PARAM_COLLECT,
              "参数 'input' 校验失败：路径不存在。"
              "请检查文件名是否正确。")
```

### 4.4 执行失败后的错误恢复流程

```
[SCRIPT_PREVIEW]
  │
  │ 用户："Y"
  ▼
CLI 层执行脚本
  │
  └──→ 失败（returncode=1，stderr="Unable to open datasource..."）
          │
          ▼
  Session.with_state(ERROR_RECOVERY)
  Session.with_error(ExecutionErrorContext)
          │
          ▼
  [ERROR_RECOVERY] 首次进入（user_input="Y"，diagnosis=None）
          │
          ▼
  _handle_error_recovery()
          │
          ├──→ analyze_execution_error() (不传 history, DC-0106) → ErrorDiagnosis
          │       ├── cause: "输入文件不存在"
          │       ├── suggestion: "请使用绝对路径或确认文件在工作空间内"
          │       ├── fixed_params: {"input": "C:\\data\\roads.shp"}
          │       ├── confidence: 0.85
          │       └── can_auto_fix: True
          │
          └──→ 返回 (ERROR_RECOVERY,
                      "执行失败诊断\n\n"
                      "原因：输入文件不存在\n"
                      "建议：请使用绝对路径...\n\n"
                      "请选择：\n"
                      "1. 确认修正（重新生成脚本预览）\n"
                      "2. 手动修改参数\n"
                      "3. 放弃任务")
          │
          ▼
  用户："1"
          │
          ▼
  _handle_error_recovery()
          │
          ├──→ 解析选择 → 确认修正
          ├──→ 应用 fixed_params → Session.with_param("input", "C:\\data\\roads.shp")
          └──→ 返回 (SCRIPT_PREVIEW, "脚本内容：...")
          │
          ▼
  [SCRIPT_PREVIEW] → 用户确认 Y → 重新执行
```

**不可自动修复的场景**（`can_auto_fix=False`）：
```
[ERROR_RECOVERY]
  │
  └──→ analyze_execution_error() → ErrorDiagnosis
          ├── cause: "GDAL 版本不支持该驱动"
          ├── suggestion: "请升级 GDAL 至 3.8+"
          ├── fixed_params: {}
          ├── confidence: 0.9
          └── can_auto_fix: False
          │
          └──→ 返回 (ERROR_RECOVERY,
                      "此错误无法自动修复。请选择：\n"
                      "1. 手动修改参数后重试\n"
                      "2. 放弃任务")
```

---

## 5. 依赖关系

### 5.1 向上依赖

| 模块 | 接口 | 用途 |
|------|------|------|
| `llm` | `classify_intent()` | 意图分类（不传 history，DC-0106） |
| `llm` | `extract_params()` | 参数抽取（不传 history，DC-0106） |
| `llm` | `LLMClient`, `PromptBuilder` | 传参给 classify/extract |
| `workspace` | `Workspace` | file_path 参数存在性校验（must_exist） |
| `config` | `get_config()` | 读取意图置信度阈值等配置 |

### 5.2 向下暴露

| 接口 | 使用方 |
|------|--------|
| `SessionProcessor.process()` | `cli/`（主循环每轮调用） |
| `TemplateRegistry` | `cli/`（启动时初始化）、`llm/`（获取可用模板列表） |
| `ParamValidator` | `SessionProcessor` 内部使用 |
| `Session`, `SessionState` | `cli/`（主循环状态判断） |
| `TemplateDef`, `ParamDef` | `templates/`（模板渲染时读取参数） |

---

## 6. 异常与错误处理

| 异常类型 | 触发条件 | 处理策略 |
|---------|---------|---------|
| `ValueError` | Session.state 为无效值 | 内部逻辑错误，打印堆栈后返回 IDLE |
| `KeyError` | 模板注册表中 template_id 不存在 | 视为意图分类错误，返回 IDLE 并提示 |
| `PathNotFoundError` | must_exist 文件不存在 | 参数校验器捕获，转为友好错误消息返回用户，提示检查文件名 |
| `LLMResponseError` | 意图分类/参数抽取返回非预期格式 | 向用户提示"理解失败，请重试"，保持在当前状态 |
| `LLMConnectionError` | LLM 网络错误 | 向用户提示网络问题，保持在当前状态 |

---

## 7. 测试策略

### 7.1 单元测试覆盖

| 测试场景 | 验证点 |
|---------|--------|
| 状态转换：IDLE → PARAM_COLLECT | 高置信度意图分类后状态正确变更 |
| 状态转换：IDLE → INTENT_CONFIRM | 低置信度时进入澄清状态，含候选列表 |
| 状态转换：INTENT_CONFIRM → PARAM_COLLECT | 用户选择后模板正确设置 |
| 状态转换：PARAM_COLLECT → SCRIPT_PREVIEW | 所有必填参数收集完成 |
| 参数校验通过 | file_path 类型通过 Workspace 校验 |
| 参数校验失败 | 路径越界时返回错误消息，状态不变 |
| 默认值填充 | 可选参数未提供时使用默认值 |
| 会话不可变性 | with_* 方法返回新实例，原实例不变 |
| 无效状态处理 | 传入未知状态时抛 ValueError |
| **参数前置提示** | 进入 PARAM_COLLECT 时响应包含参数名称、必填/可选标识、默认值、描述 |
| **空匹配处理** | LLM 返回空 template_id 时进入 INTENT_CONFIRM，响应包含用户原输入和候选列表 |
| **错误恢复：首次进入触发诊断** | ERROR_RECOVERY 且 diagnosis=None 时调用 analyze_execution_error，结果显示选项菜单 |
| **错误恢复：确认修正** | 用户选"1" + can_auto_fix=True → 应用 fixed_params → SCRIPT_PREVIEW |
| **错误恢复：手动修改** | 用户选"2" → PARAM_COLLECT，error_context 清除，保留 template + params |
| **错误恢复：放弃** | 用户选"3" → IDLE，清除 error_context + template + params |
| **错误恢复：不可自动修复** | can_auto_fix=False 时不显示"确认修正"选项，只显示手动修改/放弃 |

### 7.2 集成测试场景

- 端到端会话：模拟完整对话 → 验证最终生成的参数集合正确
- 模板注册表加载：验证所有模板文件存在且 JSON 有效
- 多轮追问：模拟缺失多个参数 → 验证逐轮追问和收集

### 7.3 Mock 策略

- `LLMClient` mock：返回预设的 IntentResult / ParamResult
- `Workspace` mock：固定根目录，简化路径校验
- `TemplateRegistry`：使用内存中的测试注册表（不读文件）

---

## 8. 需求追溯表

| 需求 ID | 设计决策 | 代码文件/函数 | 说明 |
|:-------:|:--------:|:-------------:|------|
| F2 | DC-0040, DC-0044, DC-0106 | `SessionProcessor._handle_idle()` | 意图分类与澄清（不传 history） |
| F3 | DC-0040, DC-0042, DC-0106 | `SessionProcessor._handle_param_collect()` | 参数抽取与校验（不传 history） |
| F8 | DC-0043, DC-0107 | `Session.history`, `Session.qa_history` | 会话上下文：流程历史 + QA 历史分离 |
| F9 | DC-0040 | 状态机预留扩展 | 多步任务栈（预留） |
| P1 | DC-0041 | `TemplateRegistry` | 模板化命令映射 |
| P2 | DC-0040 | SCRIPT_PREVIEW 状态 | 先展后行 |
| CODE-2 | DC-0042 | `validate_file_path` | 路径规范化 + must_exist 校验 |
| CODE-3 | — | 仅依赖 llm/ 层 | LLM 调用不外泄 |
| F10 | DC-0048, DC-0049, DC-0106 | `SessionProcessor._handle_error_recovery()` | 执行失败后保留上下文，LLM 诊断 + 用户选择修复路径（不传 history） |

---

## 附录：变更记录

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.0.8 | 2026-06-02 | 新增 DC-0106：一次性 LLM 决策调用（classify_intent / extract_params / analyze_execution_error）取消 history 参数，改为单轮调用；新增 DC-0107：Session 模型增加独立 `qa_history` 字段，Discovery/Exec 流程历史与 QATab 多轮对话历史分离；§3.1 更新 Session 数据模型；§3.5 更新 handler 说明；§8 更新需求追溯表 |
| v1.0.7 | 2026-05-30 | 新增 DC-0098：两阶段匹配（关键词粗筛 + LLM 精排）+ 自动决策（confidence ≥ 0.85 直接进入 PARAM_COLLECT）；更新 DC-0044 以兼容两阶段分支；§3.5 更新 `_handle_idle()` 行为描述 |
| v1.0.6 | 2026-05-30 | 新增 DC-0095：`TemplateRegistry` 支持运行时重扫描（`rescan()`），`api/dependencies.py` 新增 `refresh_registry()`；§3.2 更新 `TemplateRegistry` 接口定义；支持 J2 模板生成器保存后热加载（plan-j2-generate DC-0093） |
| v1.0.5 | 2026-05-29 | 新增 DC-0070：`SessionProcessor` 新增 `output_fn` 可选参数和 `set_output_fn()` 后置设置方法；Q&A 路由将 callback 透传至 `answer_question(on_chunk=...)`；§3.4 更新 `SessionProcessor` 接口定义 |
| v1.0.4 | 2026-05-28 | 新增 DC-0048/DC-0049：执行失败后进入 `ERROR_RECOVERY` 状态，保留 template + params 上下文；`_handle_error_recovery()` 统一处理 LLM 诊断和用户选择修复路径；新增 `ExecutionErrorContext` 数据模型 |
| v1.0.2 | 2026-05-28 | 空匹配（无精确对应模板）不再直接拒绝，改为进入 INTENT_CONFIRM 展示候选列表，附带友好说明 |
| v1.0.1 | 2026-05-28 | 进入 PARAM_COLLECT 时增加参数前置提示（参数名、必填/可选、默认值、描述），提升参数收集阶段 UX |
| v1.0.0 | 2026-05-26 | 初版，定义状态机、模板注册表、参数校验链、会话上下文 |
| v1.0.9 | 2026-06-03 | **合并 plan-config**：新增 §9 配置子模块（DC-0001~DC-0005）；新增 §10 路径规范化策略（DC-0010R, DC-0011R），覆盖 plan-workspace 废弃后的 F7 需求；plan-config.md 归档 |

---

## 9. 配置子模块

> 本节由原 `Document/plan-config.md` 合并而来（2026-06-03）。

### 9.1 模块职责

提供全局配置管理能力：配置文件的加载、校验、分层访问，以及环境变量覆盖机制。本模块是**所有上层模块的基础设施依赖**，在进程启动时完成一次性初始化，运行期间只读。

### 9.2 设计决策

#### DC-0001: 配置文件采用 JSON 格式

**决策**: 运行时配置文件使用 JSON，位于 `SourceCode/config/config.json`。

**理由**:
- JSON 是 Python 标准库原生支持格式，文件格式本身零额外依赖（符合 P5）
- 配置结构简单，无需 YAML 的锚点引用等高级特性
- 校验与组装由 `pydantic` 处理（ADR-0004），不增加手写验证逻辑

#### DC-0002: 配置项按功能域分层

**决策**: 配置顶层按功能域分组：`llm`。

**理由**:
- 避免扁平命名空间膨胀
- 各模块只读取自己关心的子集，降低耦合

**当前分层结构**:
```json
{
  "llm": { "base_url": "", "auth_key": "", "model_name": "" }
}
```

> 注：`workspace` 域（v1.3.0）和 `api` 域（v1.2.0）已移除。工作空间概念废弃后不再需配置默认路径；后端端口由 Electron 主进程与 Python 子进程硬编码约定为 18000。

#### DC-0003: 敏感字段支持环境变量覆盖

**决策**: `llm.auth_key` 等敏感字段允许通过环境变量覆盖配置文件中的值。

**覆盖规则**:
- 环境变量名：`GISAGENT_LLM_AUTH_KEY`（前缀 `GISAGENT_` + 大写路径用 `_` 连接）
- 优先级：环境变量 > 配置文件 > 硬编码默认值

#### DC-0004: 启动时一次性校验，运行期只读

**决策**: 配置在进程启动时完成加载和校验，成功后封装为不可变对象。运行期间不允许动态修改。

#### DC-0005: 单例模式管理配置实例

**决策**: 模块内部维护一个全局 Config 单例，通过 `get_config()` 获取。

### 9.3 数据模型

```python
from pydantic import BaseModel, ConfigDict, Field, model_validator


class LLMConfig(BaseModel):
    """LLM 连接配置。"""
    model_config = ConfigDict(frozen=True)
    base_url: str = Field(..., pattern=r"^https?://")
    auth_key: str = Field(..., min_length=1)
    model_name: str = Field(..., min_length=1)


class Config(BaseModel):
    """全局配置根对象。"""
    model_config = ConfigDict(frozen=True)
    llm: LLMConfig

    @model_validator(mode="before")
    @classmethod
    def _apply_env_overrides(cls, data: dict) -> dict:
        """Apply GISAGENT_* environment variable overrides."""
        ...
```

### 9.4 公共 API

```python
from pathlib import Path
from typing import Optional


def load_config(path: Optional[Path] = None) -> Config:
    """加载并校验配置文件，初始化全局单例。

    Design: DC-0001, DC-0003, DC-0004, DC-0005, ADR-0004
    """


def get_config() -> Config:
    """获取已加载的全局配置实例。

    Design: DC-0005
    """
```

---

## 10. 路径规范化策略

> 本节补充 plan-workspace.md 废弃后的路径处理设计（F7 覆盖）。

### 10.1 设计概述

plan-workspace.md 废弃后，工作空间不再作为安全边界限制文件访问范围。用户通过文件对话框直接选择绝对路径，GIS 数据可来自任意合法位置。但**路径规范化**（消除 `.`/`..`/符号链接）仍然是必要的基础操作，由 `ParamValidator` 和模板引擎的 `safe_path` 过滤器协同完成。

### 10.2 设计决策

#### DC-0010R: 路径规范化提供统一的绝对路径解析

**决策**: `resolve_path()` 仅负责将用户输入（相对或绝对路径）解析为**规范化后的绝对路径**，不做范围限制。

**规则**:
- 绝对路径 → 直接 `resolve()` 规范化
- 相对路径 → 以当前进程 cwd 为基准拼接后 `resolve()`
- 路径存在性校验（`must_exist=True`）仅作友好提示，不作为安全拦截

**理由**:
- GIS 原始数据体积大，通常存储在专用目录，不可能全部复制到单一工作空间
- 路径规范化（消除 `.`/`..`/符号链接）确保路径可预测

#### DC-0011R: 输出文件路径由用户完全控制

**决策**: 输出路径不再默认附加时间戳，由用户通过文件对话框显式指定。

**理由**:
-  Electron 桌面应用通过 `dialog.showSaveDialog` 获取用户明确意图的路径
- 用户可见的输出位置即最终写入位置，避免"文件去哪儿了"的困惑

### 10.3 职责分配

| 组件 | 路径操作 | 说明 |
|------|---------|------|
| `ParamValidator.validate_file_path()` | 规范化 + must_exist 校验 | 参数提交时校验 |
| `safe_path_filter()` | 规范化 | 模板渲染时将相对路径转为绝对路径 |
| `ScriptSecurityChecker` | 危险模式检测 | 渲染后二次校验（SEC-5） |
