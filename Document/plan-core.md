# plan-core

| 项目 | 内容 |
|------|------|
| 版本 | v1.0.0 |
| 状态 | 设计基线 |
| 作者 | - |
| 日期 | 2026-05-26 |

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
   ├──→ Y ──→ EXECUTING ──→ 返回 IDLE
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
| `file_path` | 非空、无遍历成分、在工作空间内、must_exist 时校验存在性 | `validate_file_path` |
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

---

## 3. 接口定义

### 3.1 数据模型

```python
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional

from llm import Message


class SessionState(Enum):
    """会话状态。"""
    IDLE = auto()              # 空闲，等待用户输入
    INTENT_CONFIRM = auto()    # 意图待确认（低置信度时）
    PARAM_COLLECT = auto()     # 参数收集中
    SCRIPT_PREVIEW = auto()    # 脚本展示，等待用户确认
    EXECUTING = auto()         # 脚本执行中


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
    history: List[Message] = field(default_factory=list)
    template: Optional[TemplateDef] = None
    params: Dict[str, str] = field(default_factory=dict)
    candidates: List[TemplateDef] = field(default_factory=list)  # 澄清候选项

    def with_state(self, state: SessionState) -> "Session":
        """返回状态变更后的新 Session。"""

    def with_template(self, template: Optional[TemplateDef]) -> "Session":
        """返回选定模板后的新 Session（传 None 表示清空模板）。"""

    def with_param(self, name: str, value: str) -> "Session":
        """返回添加参数后的新 Session。"""

    def with_history(self, message: Message) -> "Session":
        """返回追加消息后的新 Session。"""

    def with_candidates(self, candidates: List[TemplateDef]) -> "Session":
        """返回更新澄清候选项后的新 Session。"""
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
    ) -> None:
        """注入依赖。"""

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

    - 高置信度（>=0.7）→ PARAM_COLLECT，告知用户已识别的任务
    - 低置信度（<0.7）→ INTENT_CONFIRM，列出候选模板让用户选择
    - 无匹配 → 保持在 IDLE，提示无法识别
    """


def _handle_intent_confirm(
    self,
    session: Session,
    user_input: str,
) -> tuple[Session, str]:
    """意图确认状态：用户从候选中选择或否认。

    - 用户选择模板 → PARAM_COLLECT
    - 用户否认 → IDLE，提示重新描述需求
    """


def _handle_param_collect(
    self,
    session: Session,
    user_input: str,
) -> tuple[Session, str]:
    """参数收集状态：抽取参数，检查完整性。

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
  ├──→ classify_intent() → confidence=0.95, template_id="shp2geojson"
  │
  ├──→ Session.with_template(shp2geojson)
  │
  └──→ 返回 (PARAM_COLLECT, "已识别任务：Shapefile 转 GeoJSON。")
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
  ├──→ classify_intent() → confidence=0.45, top3=[shp2geojson, merge_shp, clip_raster]
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
  └──→ 返回 (PARAM_COLLECT, "已选择：Shapefile 转 GeoJSON。")
```

### 4.3 参数校验失败流程

```
[PARAM_COLLECT]
  │
  │ 用户："input: /data/roads.shp"
  ▼
_process_param_collect()
  │
  ├──→ extract_params() → {input: "/data/roads.shp"}
  │
  ├──→ ParamValidator.validate(input="/data/roads.shp")
  │       └── Workspace.resolve_path("/data/roads.shp", must_exist=True)
  │           └── PathNotFoundError → 返回错误"文件不存在"
  │
  └──→ 返回 (PARAM_COLLECT,
              "参数 'input' 校验失败：路径不存在。"
              "请检查文件名是否正确。")
```

---

## 5. 依赖关系

### 5.1 向上依赖

| 模块 | 接口 | 用途 |
|------|------|------|
| `llm` | `classify_intent()` | 意图分类 |
| `llm` | `extract_params()` | 参数抽取 |
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
| F2 | DC-0040, DC-0044 | `SessionProcessor._handle_idle()` | 意图分类与澄清 |
| F3 | DC-0040, DC-0042 | `SessionProcessor._handle_param_collect()` | 参数抽取与校验 |
| F8 | DC-0043 | `Session.history` | 会话上下文 |
| F9 | DC-0040 | 状态机预留扩展 | 多步任务栈（预留） |
| P1 | DC-0041 | `TemplateRegistry` | 模板化命令映射 |
| P2 | DC-0040 | SCRIPT_PREVIEW 状态 | 先展后行 |
| CODE-2 | DC-0042 | `validate_file_path` | 路径规范化 + must_exist 校验 |
| CODE-3 | — | 仅依赖 llm/ 层 | LLM 调用不外泄 |

---

## 附录：变更记录

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.0.0 | 2026-05-26 | 初版，定义状态机、模板注册表、参数校验链、会话上下文 |
