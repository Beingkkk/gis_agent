# plan-llm

| 项目 | 内容 |
|------|------|
| 版本 | v1.1.0 |
| 状态 | 设计基线 |
| 作者 | - |
| 日期 | 2026-05-28 |

---

## 1. 设计概述

### 1.1 模块职责

封装所有与 LLM（大语言模型）的交互：客户端连接管理、Prompt 组装、意图分类、参数抽取、文档问答生成。本模块是**唯一允许直接调用 anthropic SDK 的代码单元**（CODE-3），向上层提供类型安全的纯 Python 接口。

### 1.2 所属架构层次

应用层（`llm/`）。被 core 层和 cli 层依赖，可依赖 core/ 获取模板元数据。

### 1.3 对应需求项

| 需求 ID | 需求描述 |
|:-------:|---------|
| F1 | 文档问答：基于模板元数据和 LLM 参数知识生成回答 |
| F2 | 意图识别与分类：将自然语言映射到预定义模板 |
| F3 | 参数抽取与追问：从输入中提取文件路径、坐标参考、选项等 |
| F8 | 会话内记忆：单次对话中保留上下文 |
| F11 | Agents.md 内容注入系统提示词 |
| P1 | LLM 仅负责选择模板 ID 并填充参数，不直接生成 GDAL 命令 |

---

## 2. 设计决策

### DC-0030: 使用 anthropic SDK 直接调用 Claude API

**决策**: 通过 `anthropic.Anthropic` 客户端直接与 Kimi API（Claude 兼容）通信。

**理由**:
- spec 已锁定 anthropic 为生产依赖
- Kimi API 兼容 Claude 消息格式（base_url 可配置）
- SDK 提供流式响应、错误类型等完整功能

### DC-0031: LLM 调用采用适配器模式封装

**决策**: 所有 anthropic SDK 的细节封装在 `LLMClient` 类内部，对外暴露纯业务接口（`classify_intent`、`extract_params`、`answer_question`）。

**理由**:
- 隔离外部库变化（如未来切换本地模型），上层代码不受影响
- 统一错误处理、重试、日志逻辑
- 符合 CODE-3（LLM 调用封装在 llm/ 模块）

### DC-0032: Prompt 模板以内联常量形式组织

**决策**: 系统提示词（System Prompt）和各场景的 Prompt 模板以 Python 模块级常量字符串定义，不放在外部文件中。

**理由**:
- Prompt 与代码逻辑紧密耦合，变更需同步修改
- 避免运行时文件 IO 和路径管理
- 模块级常量可被静态分析、类型检查、IDE 自动补全

**替代方案**:
- 外部 `.txt` / `.md` 文件：运行时读取，适合非技术人员编辑。但我们的 Prompt 含代码逻辑和格式化指令，非技术人员无需修改。
- Jinja2 模板：过度设计，Prompt 结构简单，字符串格式化足够。

### DC-0033: Token 预算采用硬上限 + 上下文截断

**决策**: 系统提示词 + 历史消息 + 当前输入的总 token 数超过上限时，按 FIFO 截断最旧的历史消息，保留系统提示词和最新上下文。

**理由**:
- 防止超出模型上下文窗口导致 API 错误
- 系统提示词（含安全约束）优先级最高，不可截断
- FIFO 截断符合对话直觉（久远的上下文影响小）

**预算配置**:
- 总上限：8000 tokens（Claude 3.5 Sonnet 为 200K，预留充足余量）
- 系统提示词预留：2000 tokens
- 单次用户输入上限：2000 tokens（超长输入直接拒绝）

### DC-0034: 网络错误采用指数退避重试

**决策**: 对 transient 网络错误（超时、5xx、429 限流）实施最多 3 次重试，退避间隔 1s → 2s → 4s。

**理由**:
- API 服务偶发波动，重试可提升成功率
- 指数退避避免对服务端造成冲击
- 3 次重试总等待时间 7s，仍在可接受范围

**不重试的错误**:
- 4xx 客户端错误（400、401、403）：参数或凭证问题，重试无用
- 上下文长度超限：需截断，非重试可解决

### DC-0036: 新增 `analyze_execution_error()` 接口用于执行错误诊断

**决策**: 在 `llm/` 模块新增 `analyze_execution_error()` 函数，将 `ExecutionResult` + 当前 `template` + `params` 传给 LLM，返回结构化的 `ErrorDiagnosis`。

**输入内容**:
- 执行结果：`returncode`、`stdout`、`stderr`
- 模板信息：`id`、`name`、`description`、`params` 定义
- 当前参数：已收集的所有参数键值对
- 对话历史：最近 3 轮对话（用于理解用户原始意图）

**输出格式**（JSON）:
```json
{
  "cause": "输入文件使用了相对路径，但工作空间下不存在该文件",
  "suggestion": "将 input 参数改为绝对路径 C:\\Users\\PC\\data\\roads.shp",
  "fixed_params": {"input": "C:\\Users\\PC\\data\\roads.shp"},
  "confidence": 0.85,
  "can_auto_fix": true
}
```

**Prompt 设计**:
- system prompt: "你是一名 GDAL 命令行工具的错误诊断专家。分析以下执行错误，结合当前模板和参数，判断错误根因并给出修复建议。"
- user prompt 包含：渲染后的脚本内容、执行结果、模板描述、参数定义、当前参数值
- 要求返回严格 JSON，temperature=0.1

**理由**:
- GDAL 错误信息（尤其是 stderr）往往技术性强且冗长，普通用户难以理解
- LLM 结合模板上下文能给出精确的参数修正建议（如"把相对路径改为绝对路径"）
- 结构化输出使下游代码可直接应用 `fixed_params`，无需二次解析自然语言
- 与现有 `classify_intent`、`extract_params` 保持一致的接口风格

**错误分类策略**（LLM 判定 `can_auto_fix` 的依据）:
| 错误类型 | 示例 | can_auto_fix | 说明 |
|---------|------|:------------:|------|
| 路径问题 | "Unable to open datasource" | True | 修正路径后即可重试 |
| CRS 问题 | "Failed to process SRS" | True | 修正坐标系参数 |
| 格式问题 | "unsupported driver" | True | 修正输出格式参数 |
| 权限问题 | "Permission denied" | False | 需用户手动解决系统权限 |
| GDAL 缺失功能 | "driver not compiled" | False | 需用户升级/重装 GDAL |
| 数据损坏 | "corrupt data" | False | 需用户检查源数据 |

### DC-0035: 系统提示词动态组装

**决策**: 每次请求的系统提示词由固定约束 + Agents.md 内容 + 当前 RAG 上下文动态拼接。

**组成顺序**:
1. **固定安全约束**（不可省略）：P1 模板化命令规则、P2 先展后行规则
2. **Agents.md 内容**（若有）：项目级长期记忆
3. **RAG 检索上下文**（问答场景）：相关 GDAL 文档片段
4. **当前任务上下文**（参数抽取场景）：已确认的参数和待问字段

### DC-0068: LLMClient 新增流式输出接口 `chat_stream()`

**决策**: 新增 `chat_stream()` 方法，使用 `anthropic.messages.create(..., stream=True)` 返回 `Iterator[str]`。现有 `chat()` 保持不变，供结构化 JSON 调用者使用。

**理由**:
- Anthropic SDK 原生支持流式，实现成本低
- 结构化调用（意图分类、参数抽取、错误诊断）必须等完整 JSON 才能解析，不适合流式
- 只有 Q&A 场景（自然语言输出）适合流式输出
- 分离职责：`chat()` 用于完整响应，`chat_stream()` 用于流式输出

**实现要点**:
- 复用 `_truncate_messages()` 的 token 截断逻辑
- 无重试逻辑（流式调用一旦开始无法优雅重试）
- 异常直接抛出，由调用方处理

### DC-0069: `answer_question()` 支持可选 `on_chunk` 回调流式输出

**决策**: `answer_question()` 新增 `on_chunk: Optional[Callable[[str], None]] = None` 参数。传入时内部调用 `client.chat_stream()` 逐块回调，同时累积完整文本返回。

**理由**:
- callback 是最轻量的跨层桥接方式，不破坏返回类型（仍为 `str`）
- 完整文本仍需返回，以便保存到 `session.history`
- 不传 callback 时行为完全不变（向后兼容）

---

## 3. 接口定义

### 3.1 数据模型

```python
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class IntentResult:
    """意图分类结果。"""
    template_id: str          # 模板 ID，如 "shp2geojson"
    confidence: float         # 置信度 0.0-1.0
    reasoning: str            # 分类理由（用于调试和日志）


@dataclass(frozen=True)
class ParamResult:
    """参数抽取结果。"""
    params: Dict[str, str]    # 已提取的参数键值对
    missing: List[str]        # 缺失的必填字段名
    questions: List[str]      # 向用户追问的问题列表


@dataclass(frozen=True)
class TemplateInfo:
    """轻量级模板元数据，用于意图分类。"""
    id: str
    name: str
    description: str


@dataclass(frozen=True)
class Message:
    """对话消息。"""
    role: str                 # "user" | "assistant"
    content: str


@dataclass(frozen=True)
class ErrorDiagnosis:
    """LLM 对执行错误的结构化诊断结果。

    Design:
        DC-0036
    """
    cause: str                    # 错误根因，中文，用户可读
    suggestion: str               # 修复建议
    fixed_params: Dict[str, str]  # 建议修正后的参数
    confidence: float             # 修复方案置信度 0.0-1.0
    can_auto_fix: bool            # LLM 判定是否可自动修复
```

### 3.2 LLMClient 类

```python
class LLMClient:
    """LLM 客户端封装。

    封装 anthropic SDK 的连接、请求、重试逻辑。
    进程内单例。

    Design:
        DC-0030, DC-0031, DC-0034
    """

    def __init__(self) -> None:
        """从 Config 初始化 anthropic 客户端。"""

    def chat(
        self,
        system_prompt: str,
        messages: List[Message],
        temperature: float = 0.1,
    ) -> str:
        """发送对话请求，返回模型生成的文本。

        Args:
            system_prompt: 系统提示词。
            messages: 历史消息列表（不含当前轮次）。
            temperature: 采样温度。意图分类用 0.1（低，确定性高），
                        问答用 0.3（略高，回答更自然）。

        Returns:
            模型生成的文本内容。

        Raises:
            LLMConnectionError: 网络错误，重试耗尽。
            LLMRateLimitError: 触发限流，重试耗尽。
            LLMContextError: 上下文长度超限。
            LLMAuthError: 凭证错误（401/403）。

        Design:
            DC-0033, DC-0034
        """

    def chat_stream(
        self,
        system_prompt: str,
        messages: List[Message],
        temperature: float = 0.1,
    ) -> Iterator[str]:
        """流式发送对话请求，逐块生成文本。

        使用 Anthropic SDK 的 stream=True 模式。不复用 chat() 的重试逻辑，
        因为流式调用一旦开始无法优雅重试。

        Args:
            system_prompt: 系统提示词。
            messages: 历史消息列表（不含当前轮次）。
            temperature: 采样温度。

        Yields:
            文本块（text chunk）。

        Design:
            DC-0068
        """
```

### 3.3 PromptBuilder 类

```python
class PromptBuilder:
    """系统提示词构建器。

    负责将固定约束、Agents.md、模板知识上下文组装为系统提示词。

    Design:
        DC-0032, DC-0035
    """

    def __init__(self, agents_md: Optional[str] = None) -> None:
        """Args:
            agents_md: 工作空间 Agents.md 全文，无则为 None。
        """

    def build_system_prompt(
        self,
        template_context: Optional[str] = None,
        task_context: Optional[str] = None,
    ) -> str:
        """组装系统提示词。

        Args:
            template_context: 模板元数据上下文（问答场景）。
            task_context: 当前任务状态描述（参数抽取场景）。

        Returns:
            完整的系统提示词字符串。
        """
```

### 3.4 业务接口函数

```python
from typing import List, Optional


class TemplateInfo(NamedTuple):
    """轻量级模板元数据，用于意图分类 Prompt。"""
    id: str
    name: str
    description: str


def classify_intent(
    user_input: str,
    available_templates: List[TemplateInfo],
    history: List[Message],
    client: LLMClient,
    builder: PromptBuilder,
) -> IntentResult:
    """将用户输入分类到预定义模板。

    Args:
        user_input: 当前用户输入。
        available_templates: 可用模板元数据列表（含 id、name、description），
            供 LLM Prompt 中的意图分类参考。
        history: 对话历史。
        client: LLM 客户端。
        builder: Prompt 构建器。

    Returns:
        分类结果，含模板 ID 和置信度。

    Design:
        F2, P1
    """


def extract_params(
    user_input: str,
    template_id: str,
    param_schema: Dict,         # 来自模板注册表的参数定义
    current_params: Dict[str, str],
    history: List[Message],
    client: LLMClient,
    builder: PromptBuilder,
) -> ParamResult:
    """从用户输入中提取模板参数，识别缺失的必填字段。

    Args:
        user_input: 当前用户输入（可能是对追问的回答）。
        template_id: 已确认的模板 ID。
        param_schema: 参数 Schema（字段名、类型、必填、描述）。
        current_params: 已收集到的参数。
        history: 对话历史。
        client: LLM 客户端。
        builder: Prompt 构建器。

    Returns:
        参数抽取结果，含已提取、缺失和追问列表。

    Design:
        F3
    """


def answer_question(
    user_input: str,
    template_infos: List[TemplateInfo],
    history: List[Message],
    client: LLMClient,
    builder: PromptBuilder,
    on_chunk: Optional[Callable[[str], None]] = None,
) -> str:
    """基于模板元数据生成问答回答。

    基础概念类问题直接由 LLM 参数知识回答；
    用法指导类问题基于匹配模板的元数据生成回答。

    当 *on_chunk* 不为 None 时，通过流式 API 逐块输出，同时累积完整文本返回。

    Args:
        user_input: 用户问题。
        template_infos: 匹配到的模板元数据列表（含 id、name、description、
            concept、note、common_error 等）。
        history: 对话历史。
        client: LLM 客户端。
        builder: Prompt 构建器。
        on_chunk: 可选的逐块输出回调（用于流式输出）。

    Returns:
        自然语言回答（完整文本）。

    Design:
        F1, P4, DC-0069
    """


def analyze_execution_error(
    execution_result: ExecutionResult,
    template: TemplateDef,
    current_params: Dict[str, str],
    history: List[Message],
    client: LLMClient,
    builder: PromptBuilder,
) -> ErrorDiagnosis:
    """分析 GDAL 脚本执行错误，输出结构化诊断。

    将 ExecutionResult（returncode、stdout、stderr）与当前 template/params
    一起传给 LLM，让模型结合 GDAL 知识诊断根因并建议修复。

    Args:
        execution_result: ScriptExecutor.execute() 的返回结果。
        template: 当前已确认的模板定义。
        current_params: 当前已收集的参数。
        history: 对话历史。
        client: LLM 客户端。
        builder: Prompt 构建器。

    Returns:
        ErrorDiagnosis，含根因、建议、修正后参数、置信度、可自动修复标志。

    Design:
        DC-0036
    """
```

### 3.5 异常类型

```python
class LLMError(Exception):
    """LLM 模块基础异常。"""


class LLMConnectionError(LLMError):
    """网络连接错误（超时、DNS 失败等）。"""


class LLMRateLimitError(LLMError):
    """API 限流（429）。"""


class LLMContextError(LLMError):
    """上下文长度超限。"""


class LLMAuthError(LLMError):
    """认证失败（401/403）。"""


class LLMResponseError(LLMError):
    """响应解析失败（非预期格式）。"""
```

---

## 4. 数据流与控制流

### 4.1 意图分类流程

```
用户输入："把这三个省的 shp 合并成一个 GeoJSON"
    │
    ▼
classify_intent()
    │
    ├──→ PromptBuilder.build_system_prompt()
    │       ├── 固定约束："你只能从以下模板中选择..."
    │       └── Agents.md（若有）
    │
    ├──→ 构造 user prompt：
    │       "可用模板：[shp2geojson, merge_shp, clip_raster, ...]
    │        用户输入：把这三个省的 shp 合并成一个 GeoJSON
    │        请分析用户意图，从可用模板中选择最匹配的一个。
    │        评分规则：confidence≥0.7 高度匹配，0.3-0.7 有关联但不完全匹配，
    │        <0.3 关联度很低。即使不完全匹配也请返回最接近的模板，
    │        不要留空 template_id。
    │        请输出 JSON：{template_id, confidence, reasoning}"
    │
    ├──→ LLMClient.chat(temperature=0.1)
    │       ├── 尝试请求 → 失败 → 指数退避重试（最多3次）
    │       └── 成功 → 返回 JSON 字符串
    │
    ├──→ 解析 JSON（严格模式，非 JSON 则抛 LLMResponseError）
    │
    └──→ 验证 template_id 在可用列表中
            │
            ├── 有效 → 返回 IntentResult
            └── 非法（LLM 返回了列表外的 ID）→ confidence 置 0，template_id 为空
```

### 4.2 参数抽取流程

```
用户输入："输出叫 roads_out.json"
    │
    ▼
extract_params()
    │
    ├──→ PromptBuilder.build_system_prompt(task_context=当前状态)
    │       └── 任务上下文："当前模板：shp2geojson，已收集参数：..."
    │
    ├──→ 构造 user prompt：
    │       "参数 Schema：{input: {type: file_path, required: true}, ...}
    │        已收集：{input: 'roads.shp'}
    │        用户输入：输出叫 roads_out.json
    │        请输出 JSON：{params, missing, questions}"
    │
    ├──→ LLMClient.chat(temperature=0.1)
    │
    ├──→ 解析 JSON
    │
    └──→ 类型校验（file_path 值需通过 Workspace.resolve_path 二次校验）
            │
            └──→ 返回 ParamResult
```

### 4.3 文档问答流程

```
用户输入："ogr2ogr 能输出哪些格式？"
    │
    ▼
模板匹配（基于 intent 相似度或关键词匹配）
    │
    ├──→ 匹配到相关模板 → 提取模板元数据
    │       └── id, name, description, @concept, @note, @common_error
    │
    └──→ 未匹配到模板 → 标记为"概念性问题"（走 LLM 参数知识）
            │
            ▼
    answer_question()
            │
            ├──→ PromptBuilder.build_system_prompt(template_context=模板元数据)
            │       ├── 固定约束："基于以下模板元数据回答用法问题；
            │       │              若为基础概念，使用你的参数知识回答；
            │       │              不要编造模板中未定义的参数"
            │       └── 模板上下文："模板: shp2geojson\n描述: ...\n概念: ..."
            │
            ├──→ 构造 user prompt：用户原始问题
            │
            ├──→ LLMClient.chat(temperature=0.3)
            │
            └──→ 返回自然语言回答（不经过 JSON 解析）
```

### 4.4 错误诊断流程

```
[执行失败]
  │
  ▼
analyze_execution_error()
  │
  ├──→ PromptBuilder.build_system_prompt()
  │       └── 固定约束："你是一名 GDAL 命令行工具的错误诊断专家..."
  │
  ├──→ 构造 user prompt：
  │       "模板：shp2geojson（Shapefile 转 GeoJSON）
  │        参数定义：{input: file_path(required), output: file_path(required), ...}
  │        当前参数：{input: 'roads.shp', output: 'out.geojson'}
  │        渲染后脚本：ogr2ogr -f 'GeoJSON' out.geojson roads.shp
  │        执行结果：
  │          returncode: 1
  │          stderr: ERROR 1: Unable to open datasource `roads.shp'...
  │        请分析错误根因，输出 JSON：
  │        {cause, suggestion, fixed_params, confidence, can_auto_fix}"
  │
  ├──→ LLMClient.chat(temperature=0.1)
  │       └── 返回 JSON 字符串
  │
  ├──→ 解析 JSON（同 classify_intent：strip markdown code block → json.loads）
  │       └── 失败 fallback → ErrorDiagnosis(
  │               cause="诊断失败，请手动检查错误输出",
  │               suggestion="",
  │               fixed_params={},
  │               confidence=0.0,
  │               can_auto_fix=False)
  │
  └──→ 返回 ErrorDiagnosis
```

**fallback 策略**：
- JSON 解析失败 → 生成一个保守的 diagnosis（can_auto_fix=False，cause 提示诊断失败）
- LLM 返回的 fixed_params 包含不在当前模板参数列表中的 key → 过滤掉非法 key
- confidence < 0.5 时视为不可信，can_auto_fix 强制置 False

### 4.5 Token 预算截断流程

```
构建请求前计算预估 token
    │
    ├──→ 系统提示词 + 历史消息 + 当前输入
    │
    ├──→ 总数 <= 8000 → 直接发送
    │
    └──→ 总数 > 8000
            │
            ├──→ 保留系统提示词（不可截断）
            │
            ├──→ 从 oldest 历史消息开始移除
            │       └── 每次移除一条，重新计算，直到 <= 8000
            │
            └──→ 若移除所有历史仍超限
                    └──→ 截断当前输入至 2000 tokens
                            └── 仍超限 → 抛 LLMContextError
```

---

## 5. 依赖关系

### 5.1 向上依赖

| 模块 | 接口 | 用途 |
|------|------|------|
| `config` | `get_config()` | 读取 LLM 连接参数 |
| `core` | `TemplateDef`（模板元数据） | 文档问答时获取模板知识上下文 |
| `workspace` | `Workspace.load_agents_md()` | 获取 Agents.md 内容 |

### 5.2 向下暴露

| 接口 | 使用方 |
|------|--------|
| `classify_intent()` | `core/`（状态机中调用） |
| `extract_params()` | `core/`（状态机中调用） |
| `answer_question()` | `cli/`（问答场景直接调用） |
| `LLMClient.chat()` | 本模块内部（`classify_intent` 等调用） |
| `Message` | `cli/`、`core/`（传递对话历史） |

---

## 6. 异常与错误处理

| 异常类型 | 触发条件 | 处理策略 |
|---------|---------|---------|
| `LLMConnectionError` | 网络超时/DNS 失败，3 次重试耗尽 | CLI 向用户提示"网络连接失败，请检查网络后重试" |
| `LLMRateLimitError` | 429 限流，3 次重试耗尽 | 提示"服务繁忙，请稍后再试" |
| `LLMAuthError` | 401/403 认证失败 | 提示"API 凭证无效，请检查 config.json 中的 auth_key" |
| `LLMContextError` | 上下文长度超限且无法截断 | 提示"对话过长，请使用 /clear 清除上下文后重试" |
| `LLMResponseError` | 返回非预期格式（如非 JSON） | 记录原始响应，提示"模型响应异常，请重试" |
| `json.JSONDecodeError` | 响应解析失败 | 同上 |

---

## 7. 测试策略

### 7.1 单元测试覆盖

| 测试场景 | 验证点 |
|---------|--------|
| 意图分类 Prompt 构建 | 系统提示词包含模板列表和安全约束 |
| 参数抽取 Prompt 构建 | 包含参数 Schema 和当前收集状态 |
| Token 截断 | 超长历史被正确移除，系统提示词保留 |
| 指数退避重试 | mock 超时错误，验证调用 3 次且间隔递增 |
| 不重试 4xx | mock 401，验证只调用 1 次 |
| JSON 解析失败 | 非 JSON 响应时抛 LLMResponseError |
| 无效 template_id | 返回的 ID 不在列表中时 confidence=0 |
| **模板知识问答** | 匹配到模板时，回答基于模板元数据；未匹配时基于 LLM 参数知识 |
| **流式输出** | `chat_stream()` 逐块 yield 文本；`answer_question(on_chunk=...)` 回调被正确调用 |
| **错误诊断 Prompt 构建** | 系统提示词包含 GDAL 诊断专家角色，user prompt 包含模板/参数/执行结果 |
| **错误诊断 JSON 解析** | markdown code block 被 strip，解析失败时 fallback 到保守 diagnosis |
| **错误诊断非法 key 过滤** | fixed_params 包含不在模板参数列表中的 key 时被过滤 |
| **错误诊断低置信度处理** | confidence < 0.5 时 can_auto_fix 强制置 False |

### 7.2 集成测试场景

- 端到端意图分类：模拟 API 响应 → 验证返回 IntentResult
- 端到端参数抽取：模拟多轮对话 → 验证参数渐进收集
- Agents.md 注入：验证系统提示词包含 Agents.md 内容

### 7.3 Mock 策略

- `LLMClient` 整体 mock：直接返回预设的 JSON 字符串，跳过网络请求
- `anthropic.Anthropic` patch：验证请求参数（temperature、messages 格式）
- `core.TemplateRegistry` mock：返回预设的 TemplateDef 列表（用于问答模板匹配）

---

## 8. 需求追溯表

| 需求 ID | 设计决策 | 代码文件/函数 | 说明 |
|:-------:|:--------:|:-------------:|------|
| F1 | DC-0035 | `answer_question()` | 基于模板元数据和 LLM 参数知识的文档问答 |
| F2 | DC-0031, DC-0032 | `classify_intent()` | 意图分类 |
| F3 | DC-0031, DC-0032 | `extract_params()` | 参数抽取与追问 |
| F8 | DC-0033 | Token 截断逻辑 | 会话记忆上下文管理 |
| F10 | DC-0036 | `analyze_execution_error()` | 执行错误 LLM 诊断 + 结构化修复建议 |
| F11 | DC-0035 | `PromptBuilder` | Agents.md 注入系统提示词 |
| P1 | DC-0032 | 系统提示词固定约束 | 模板化命令规则 |
| P4 | DC-0035 | `answer_question()` 模板上下文 | 基于模板元数据回答用法问题 |
| CODE-3 | DC-0031 | `LLMClient` 封装 | anthropic SDK 不外泄 |
| SEC-1 | DC-0030 | Config 读取 auth_key | 不硬编码 API Key |

---

## 附录：变更记录

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.3.0 | 2026-05-29 | 新增 DC-0068/DC-0069：LLMClient 新增 `chat_stream()` 流式接口；`answer_question()` 新增 `on_chunk` 回调参数；§3.2 更新 LLMClient 接口、§3.4 更新 `answer_question` 签名、§7 新增流式测试 |
| v1.2.0 | 2026-05-28 | 新增 DC-0036：`analyze_execution_error()` 接口，将 ExecutionResult + template + params 传给 LLM，返回结构化 `ErrorDiagnosis`；新增 §3.1 `ErrorDiagnosis`、§3.4 `analyze_execution_error()`、§4.4 错误诊断流程、§7.1 测试策略、§8 需求追溯 |
| v1.1.1 | 2026-05-28 | `classify_intent` Prompt 改进：不再要求 LLM 留空 template_id，而是始终返回最接近的模板并用 confidence 反映匹配程度；§4.1 数据流更新 |
| v1.1.0 | 2026-05-28 | 新增 `extract_keywords()` 接口（§3.4、§4.3、§7）；更新文档问答流程为关键词提炼 + 多路召回；更新需求追溯表 |
| v1.0.0 | 2026-05-26 | 初版，定义 LLM 封装、Prompt 管理、意图分类、参数抽取、文档问答接口 |
