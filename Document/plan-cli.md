# plan-cli

| 项目 | 内容 |
|------|------|
| 版本 | v1.0.1 |
| 状态 | 设计基线 |
| 作者 | - |
| 日期 | 2026-05-28 |

---

## 1. 设计概述

### 1.1 模块职责

实现 GIS Agent 的命令行界面：启动参数解析、REPL 交互循环、斜杠命令处理、用户确认流程、脚本执行沙箱（含 dry-run 模式）。本模块是**用户与系统交互的唯一入口**，负责将用户输入传递给核心层状态机，并将系统响应呈现给用户。

### 1.2 所属架构层次

CLI 层（`cli/`）。可依赖所有下层模块（core、llm、rag、workspace）。

### 1.3 对应需求项

| 需求 ID | 需求描述 |
|:-------:|---------|
| F5 | 向用户完整展示脚本内容，要求明确确认（Y/N）后执行 |
| F6 | 支持 `--dry-run` 空跑模式 |
| F7 | 支持启动时指定工作空间（`--workspace`） |
| F8 | 会话内记忆（多轮追问和补充） |
| P2 | 先展后行：任何脚本必须展示并获得确认 |
| P3 | 所有操作强制限制在工作空间内 |
| W1-W3 | 工作空间相关约束 |

---

## 2. 设计决策

### DC-0060: 启动参数使用 argparse 标准库解析

**决策**: 使用 Python 标准库 `argparse` 解析命令行参数：`--workspace`、`--config`、`--dry-run`。

**理由**:
- 零额外依赖（符合 P5）
- 内部工具参数简单，`argparse` 完全够用
- 自动生成 `--help` 帮助信息

### DC-0061: 主循环采用 REPL 模式

**决策**: 程序启动后进入 Read-Eval-Print Loop，持续读取用户输入直至显式退出。

**理由**:
- GIS Agent 是多轮对话工具，非一次性命令执行
- REPL 模式天然支持追问、澄清、上下文保留
- 参考 OpenClaw 的 Main Loop 设计思想

**循环结构**:
```python
def repl_loop(session: Session) -> None:
    while True:
        user_input = input("GIS> ")
        if user_input.startswith("/"):
            handle_slash_command(user_input, session)
            continue
        new_session, response = processor.process(session, user_input)
        print(response)
        session = new_session
        if session.state == SessionState.EXECUTING:
            execute_or_preview(session)
            session = session.with_state(SessionState.IDLE)
```

### DC-0062: 斜杠命令作为 REPL 的内建指令

**决策**: 以 `/` 开头的输入视为系统命令，不传递给状态机处理。

**理由**:
- 提供与对话分离的系统控制入口
- 用户熟悉此类交互（如 IRC、Discord、Claude Code）
- 不影响自然语言对话的语义

**命令列表**:
| 命令 | 功能 |
|------|------|
| `/quit` 或 `/q` | 退出程序 |
| `/clear` | 清除会话历史，重置为 IDLE 状态 |
| `/workspace` | 显示当前工作空间路径 |
| `/templates` | 列出可用模板 |
| `/status` | 显示当前状态、工作空间、历史轮数 |
| `/init` | 将当前会话的任务意图、模板、参数写入 Agents.md |
| `/help` | 显示帮助信息 |

### DC-0063: 脚本执行使用 subprocess，cwd 限定在工作空间

**决策**: 用户确认后，通过 `subprocess.run()` 执行渲染后的脚本，`cwd` 参数设为工作空间根目录。

**理由**:
- `subprocess` 是标准库，提供进程隔离
- `cwd` 参数确保 GDAL 命令在工作空间内执行
- `timeout` 参数防止长时间挂起
- 可捕获 stdout/stderr 用于错误诊断（F10）

**执行失败后流程扩展**（DC-0063 扩展）：
- `ScriptExecutor.execute()` 返回 `ExecutionResult`，`REPL._execute_script()` 检查 `result.success`
- 失败时：构造 `ExecutionErrorContext`，设置 `session.state = ERROR_RECOVERY`，`session.error_context = ctx`
- 不直接返回 IDLE，将错误恢复逻辑委托给 `SessionProcessor._handle_error_recovery()`（plan-core DC-0049）

### DC-0064: dry-run 模式只展示不执行

**决策**: `--dry-run` 标志使程序在 SCRIPT_PREVIEW 状态时直接展示脚本并提示"dry-run 模式，跳过执行"，然后返回 IDLE。

**理由**:
- 用户可在安全环境下验证脚本内容
- 不修改任何文件，便于调试
- 符合 F6 要求

### DC-0065: 脚本执行设置超时控制

**决策**: 单次脚本执行设置 300 秒（5 分钟）超时，超时后强制终止并提示用户。

**理由**:
- GDAL 处理大文件可能耗时较长
- 防止异常挂起占用资源
- 超时时间可配置（放入 Config）

### DC-0066: 用户确认采用严格 Y/N 输入

**决策**: SCRIPT_PREVIEW 状态下，展示脚本后循环读取用户输入，仅接受 `Y` 或 `N`（大小写不敏感），其他输入提示重新选择。

**理由**:
- 避免误触（如空输入、意外字符）导致意外执行
- 明确性：用户必须主动输入 `Y` 才能继续
- 符合 P2 的先展后行原则

### DC-0071: REPL 暴露 `output_fn` 供 Processor 流式输出使用

**决策**: REPL 类新增 `output_fn` 只读 property，返回构造时传入（或默认的 `print`）输出函数。`main()` 在构建 REPL 后，通过 `processor.set_output_fn(repl.output_fn)` 将该函数注入 SessionProcessor，使 Q&A 路由可流式输出。

**理由**:
- REPL 已拥有输出函数，只需暴露即可复用
- 后置注入避免构造顺序依赖（SessionProcessor 先于 REPL 创建）
- 无输出函数注入时流式功能静默禁用，不影响现有行为

**实现要点**:
- `REPL.output_fn` property 返回 `self._output_fn`
- `main()` 中 `processor.set_output_fn(repl.output_fn)` 完成接线

### DC-0067: `/init` 命令将会话快照持久化到 Agents.md

**决策**: 提供 `/init` 斜杠命令，将当前 Session 中的任务意图、匹配模板、收集到的参数追加写入工作空间的 `Agents.md`。文件不存在时自动创建。

**理由**:
- Agents.md 作为项目级长期记忆，当前仅支持手动编写，门槛高
- 用户在完成一轮有意义的对话后，通过 `/init` 一键固化配置，降低维护成本
- 追加模式不覆盖已有内容，支持多任务记录
- 无模板时（IDLE 状态）拒绝写入，避免生成空记录

**写入内容格式**:
```markdown
## 任务记录 — 2026-05-28 14:32:15

- **意图**: Shapefile 转 GeoJSON
- **模板**: shp2geojson
- **参数**:
  - input (file_path, 必填): roads.shp — 输入 Shapefile 路径
  - output (file_path, 必填): roads_out.geojson — 输出 GeoJSON 路径
  - t_srs (crs, 可选, 默认 EPSG:4326): EPSG:4326 — 目标坐标系
```

**边界处理**:
| 场景 | 行为 |
|------|------|
| Session 无 template（还在 IDLE/INTENT_CONFIRM） | 提示"当前没有已确认的任务，请先描述需求并完成参数收集" |
| Agents.md 不存在 | 自动创建，写入文件头 `# GIS Agent 项目配置` + 任务记录 |
| Agents.md 已存在 | 追加到末尾，不覆盖 |
| 参数值为空字符串 | 值记为"(未提供)"，但保留参数名和类型 |
| 写入失败（权限等） | 捕获 OSError，提示具体错误，不抛异常 |

---

## 3. 接口定义

### 3.1 启动参数

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class CLIArgs:
    """解析后的命令行参数。"""
    workspace: Optional[Path] = None
    config: Optional[Path] = None
    dry_run: bool = False
```

### 3.2 入口函数

```python
def main(argv: Optional[list[str]] = None) -> int:
    """CLI 入口函数。

    执行流程：
    1. 解析命令行参数
    2. 加载配置（config.load_config）
    3. 初始化工作空间（workspace.initialize）
    4. 初始化 RAG 检索器（rag.get_retriever）
    5. 初始化 LLM 客户端和 Prompt 构建器
    6. 定位模板目录（由包路径推导 ``{pkg_root}/data/templates/``）
    7. 扫描模板文件并构建 TemplateRegistry
    8. 构建 SessionProcessor（含 TemplateRegistry、ParamValidator、LLMClient、PromptBuilder、TemplateEngine）
    9. 构建 ScriptExecutor（含 workspace）
   10. 启动 REPL 循环（注入 SessionProcessor + ScriptExecutor）

    Args:
        argv: 命令行参数列表。默认为 sys.argv[1:]。

    Returns:
        进程退出码。0 为正常退出，1 为异常退出，2 为参数错误。

    Design:
        DC-0060, DC-0061
    """
```

### 3.3 REPL 循环

```python
class REPL:
    """交互式 REPL 循环。

    管理用户输入读取、斜杠命令分发、状态机调用、响应输出。

    Design:
        DC-0061, DC-0062
    """

    def __init__(
        self,
        processor: SessionProcessor,
        executor: ScriptExecutor,
        dry_run: bool = False,
    ) -> None:
        """注入依赖。

        Args:
            processor: 会话状态处理器。
            executor: 脚本执行器（用于 SCRIPT_PREVIEW 状态的执行/预览）。
            dry_run: 是否空跑模式。
        """

    @property
    def output_fn(self) -> Callable[[str], None]:
        """返回输出函数，用于注入 Processor 实现流式输出（DC-0071）。"""

    def run(self) -> None:
        """启动 REPL 循环，直至用户退出。"""

    def _read_input(self) -> str:
        """读取用户输入，处理 EOF（Ctrl+D）和 KeyboardInterrupt（Ctrl+C）。"""

    def _print_response(self, response: str) -> None:
        """输出系统响应到 stdout。"""

    def _handle_slash_command(self, command: str, session: Session) -> Session:
        """处理斜杠命令，返回可能变更的 Session。"""

    def _handle_execution(self, session: Session) -> Session:
        """处理 SCRIPT_PREVIEW → 执行/预览 → 返回 IDLE 的流程。"""
```

### 3.4 脚本执行器

```python
@dataclass(frozen=True)
class ExecutionResult:
    """脚本执行结果。"""
    success: bool
    returncode: int
    stdout: str
    stderr: str
    duration_ms: int


class ScriptExecutor:
    """脚本执行器。

    负责在安全沙箱中执行渲染后的 GDAL 脚本。

    Design:
        DC-0063, DC-0065
    """

    def __init__(
        self,
        workspace: Workspace,
        timeout: int = 300,
    ) -> None:
        """Args:
            workspace: 工作空间（作为 cwd）。
            timeout: 超时秒数。
        """

    def execute(self, script: RenderedScript) -> ExecutionResult:
        """执行脚本。

        Args:
            script: 渲染后的脚本对象。

        Returns:
            执行结果。

        Raises:
            subprocess.TimeoutExpired: 执行超时。
            OSError: 进程创建失败。
        """

    def preview(self, script: RenderedScript) -> None:
        """dry-run 模式下仅展示脚本，不执行。"""
```

### 3.5 斜杠命令处理器

```python
class SlashCommandHandler:
    """斜杠命令处理器。

    Design:
        DC-0062
    """

    COMMANDS: dict[str, callable] = {
        "quit": _cmd_quit,
        "q": _cmd_quit,
        "clear": _cmd_clear,
        "workspace": _cmd_workspace,
        "templates": _cmd_templates,
        "status": _cmd_status,
        "init": _cmd_init,
        "help": _cmd_help,
    }

    def handle(self, command_line: str, session: Session) -> tuple[Session, str]:
        """处理斜杠命令。

        Args:
            command_line: 完整命令行（如 "/workspace /data/gis"）。
            session: 当前会话。

        Returns:
            (new_session_or_same, response_text)
        """
```

---

## 4. 数据流与控制流

### 4.1 启动初始化流程

```
[用户执行] python -m gis_agent --workspace /data/gis
    │
    ▼
argparse 解析参数
    │
    ├──→ --config 指定？→ 使用该路径
    └──→ 未指定 → 使用默认路径
    │
    ▼
load_config(config_path)
    │
    ├──→ 成功 → 继续
    └──→ 失败 → 打印错误，退出码 2
    │
    ▼
workspace.initialize(workspace_path)
    │
    ├──→ 成功 → 继续
    └──→ 失败（目录不存在）→ 打印错误，退出码 2
    │
    ▼
打印 "正在加载文档检索系统（首次启动可能需要 1-2 分钟）..."
    │
    ▼
get_retriever()  # RAG 初始化（加载 embedding 模型 + 检查索引缓存）
    │
    ├──→ 成功 → 打印 "文档检索系统加载完成。" → 继续
    └──→ 失败（模型缺失）→ 打印错误，退出码 1
    │
    ▼
模板目录定位
    │
    ├──→ 包内默认路径：``{pkg_root}/data/templates/``
    │       （由 ``__file__`` 推导，无需用户配置）
    │
    ▼
扫描模板文件（templates.scanner.scan_templates）
    │
    ▼
构建 TemplateRegistry（扫描结果 + template_dir）
    │
    ▼
构建 SessionProcessor（注入 TemplateRegistry、ParamValidator、LLMClient、PromptBuilder）
    │
    ▼
初始化 Session（state=IDLE）
    │
    ▼
打印欢迎信息（含工作空间路径、可用模板数量、/help 提示）
    │
    ▼
启动 REPL.run()
    │
    ├──→ REPL 运行中，Q&A 场景通过 output_fn 流式输出回答
    │       └── 若未注入 output_fn（测试模式），Q&A 仍一次性返回完整文本
    │
    └──→ 正常退出
```

### 4.2 REPL 主循环流程

```
[REPL.run()]
    │
    ▼
打印 "GIS> " 提示符
    │
    ▼
读取用户输入
    │
    ├──→ EOF（Ctrl+D）→ 打印 "再见" → 退出
    ├──→ KeyboardInterrupt（Ctrl+C）→ 打印 "^C，使用 /quit 退出" → 继续循环
    └──→ 正常输入 → 继续
    │
    ▼
输入以 "/" 开头？
    │
    ├──→ 是 → SlashCommandHandler.handle() → 输出响应 → 继续循环
    └──→ 否 → 继续
    │
    ▼
SessionProcessor.process(session, user_input)
    │
    ├──→ 返回 (new_session, response)
    │
    ▼
打印 response
    │
    ▼
new_session.state == SCRIPT_PREVIEW？
    │
    ├──→ 否 → session = new_session → 继续循环
    └──→ 是 → _handle_execution(new_session)
                │
                ├──→ dry_run=True → preview() → 提示"dry-run 跳过执行"
                │       └──→ session = IDLE → 继续循环
                │
                └──→ dry_run=False
                        │
                        ├──→ 打印脚本完整内容
                        ├──→ 循环读取 Y/N
                        │       ├──→ N → session = PARAM_COLLECT → 提示修改 → 继续循环
                        │       └──→ Y → ScriptExecutor.execute()
                        │               │
                        │               ├──→ 成功 → 打印 stdout + stderr（如有）+ 耗时 → session = IDLE → 继续循环
                        │               │
                        │               └──→ 失败 → 打印返回码 + stderr + stdout（如有）+ 耗时
                        │                       │
                        │                       └──→ session = ERROR_RECOVERY（含 ExecutionErrorContext）
                        │                               │
                        │                               └──→ REPL 继续循环
                        │                                       下一轮 processor.process(session, user_input)
                        │                                       分发到 _handle_error_recovery()
                        │
                        └──→ session = 新状态 → 继续循环
```

### 4.3 用户确认交互流程

```
[SCRIPT_PREVIEW 状态]
    │
    ▼
系统打印：
"───────────────────────────────
脚本预览：
───────────────────────────────
@echo off
ogr2ogr -f "GeoJSON" ...
───────────────────────────────
确认执行？(Y/N)："
    │
    ▼
读取用户输入
    │
    ├──→ "Y" 或 "y" → 执行脚本
    ├──→ "N" 或 "n" → 返回 PARAM_COLLECT，提示"请修改参数"
    └──→ 其他 → 提示"请输入 Y 确认执行，或 N 取消" → 重新读取
```

### 4.4 脚本执行与错误处理流程

```
ScriptExecutor.execute(script)
    │
    ├──→ 将 script.content 写入临时文件（工作空间内）
    │       └── 文件名：script_20260526_143052.bat
    │
    ├──→ subprocess.run(
    │       cmd=["cmd", "/c", temp_script],
    │       cwd=workspace.root,
    │       timeout=300,
    │       capture_output=True,
    │       text=True,
    │   )
    │
    ├──→ 超时 → subprocess.TimeoutExpired
    │       └── kill 进程 → 提示"执行超时（300秒），已终止"
    │       └── 返回 ExecutionResult(success=False, returncode=-1, ...)
    │
    ├──→ 非零退出码
    │       └── 打印返回码 + stderr + stdout（如有）+ 耗时
    │       └── 返回 ExecutionResult(success=False, returncode=1, ...)
    │           └── REPL._execute_script() 构造 ExecutionErrorContext
    │                   └── session.state = ERROR_RECOVERY
    │                   └── session.error_context = ctx
    │                   └── REPL 继续循环，下一轮由 processor 处理
    │
    └──→ 退出码 0
            └── 打印 stdout + stderr（如有）+ 耗时 → 提示"执行完成"
            └── 返回 ExecutionResult(success=True, returncode=0, ...)
            └── REPL._execute_script() → session = IDLE
    │
    ▼
删除临时脚本文件（或保留用于审计）
    │
    ▼
返回 ExecutionResult
```

---

## 5. 依赖关系

### 5.1 向上依赖

| 模块 | 接口 | 用途 |
|------|------|------|
| `config` | `load_config()`, `get_config()` | 配置加载 |
| `workspace` | `initialize()`, `get_workspace()` | 工作空间初始化 |
| `rag` | `get_retriever()` | RAG 检索器初始化 |
| `llm` | `LLMClient`, `PromptBuilder` | LLM 组件初始化 |
| `core` | `TemplateRegistry`, `ParamValidator`, `SessionProcessor` | 核心组件初始化 |
| `core` | `Session`, `SessionState` | 会话状态管理 |
| `templates` | `scan_templates`, `TemplateEngine`, `RenderedScript` | 模板扫描与渲染（Registry 和 Processor 使用） |

### 5.2 向下暴露

| 接口 | 使用方 |
|------|--------|
| `main()` | `python -m gis_agent` 入口 |

CLI 层是顶层，不向下暴露接口给其他模块。

---

## 6. 异常与错误处理

| 异常类型 | 触发条件 | 处理策略 |
|---------|---------|---------|
| `WorkspaceNotFoundError` | `--workspace` 目录不存在 | 启动时捕获，打印友好错误，退出码 2 |
| `FileNotFoundError` | 配置文件不存在 | 同上 |
| `RuntimeError` | RAG 模型缺失 | 启动时捕获，提示检查 `SourceCode/model/`，退出码 1 |
| `KeyboardInterrupt` | 用户按 Ctrl+C | REPL 中捕获，提示使用 `/quit`，继续循环 |
| `EOFError` | 用户按 Ctrl+D | REPL 中捕获，正常退出（退出码 0） |
| `subprocess.TimeoutExpired` | 脚本执行超时 | 提示超时，终止进程，返回 IDLE |
| `OSError` | 进程创建失败 | 提示系统错误，返回 IDLE |

---

## 7. 测试策略

### 7.1 单元测试覆盖

| 测试场景 | 验证点 |
|---------|--------|
| 参数解析 | `--workspace`、`--config`、`--dry-run` 正确解析 |
| 参数默认值 | 未提供 `--workspace` 时使用配置默认值 |
| REPL 输入处理 | 正常输入传递给 processor |
| 斜杠命令识别 | `/quit` 被正确分发，不传递给 processor |
| 斜杠命令 `/clear` | 清除后 session 回到 IDLE，history 为空 |
| 斜杠命令 `/workspace` | 显示当前工作空间路径 |
| 斜杠命令未知 | 提示未知命令，继续循环 |
| 斜杠命令 `/init` | 有 template 时追加写入 Agents.md，无 template 时提示拒绝 |
| 斜杠命令 `/init` 文件不存在 | 自动创建 Agents.md 并写入 |
| Y 确认执行 | 调用 ScriptExecutor.execute() |
| N 取消执行 | 返回 PARAM_COLLECT 状态 |
| 无效确认输入 | 循环要求重新输入，不崩溃 |
| dry-run 模式 | 只展示不执行，直接返回 IDLE |
| Ctrl+C 处理 | 不退出，提示使用 /quit |
| Ctrl+D 处理 | 正常退出 |
| 执行失败进入 ERROR_RECOVERY | `_execute_script()` 失败时构造 `ExecutionErrorContext`，设置 `ERROR_RECOVERY` 状态 |
| 错误恢复：确认修正 | ERROR_RECOVERY 状态下用户选"1" → 应用 fixed_params → SCRIPT_PREVIEW |
| 错误恢复：手动修改 | ERROR_RECOVERY 状态下用户选"2" → PARAM_COLLECT，保留 template + params |
| 错误恢复：放弃 | ERROR_RECOVERY 状态下用户选"3" → IDLE，清除全部上下文 |
| 错误恢复：不可自动修复 | `can_auto_fix=False` 时只显示 2 个选项（手动修改/放弃） |

### 7.2 集成测试场景

- 端到端启动：指定参数 → 初始化各模块 → 进入 REPL
- 完整对话流：多轮输入 → 参数收集 → 脚本展示 → 执行 → 验证输出文件
- 错误恢复：执行失败后 → 进入 ERROR_RECOVERY → LLM 诊断 → 用户选择修复路径

### 7.3 Mock 策略

- `SessionProcessor` mock：返回预设的状态转换和响应
- `ScriptExecutor` mock：返回预设的 ExecutionResult
- `input()` mock：用预设输入序列驱动 REPL
- `subprocess.run` mock：避免实际执行命令

---

## 8. 需求追溯表

| 需求 ID | 设计决策 | 代码文件/函数 | 说明 |
|:-------:|:--------:|:-------------:|------|
| F5 | DC-0066 | `REPL._handle_execution()` | Y/N 确认后执行 |
| F5 | DC-0063 | `ScriptExecutor.execute()` | 工作空间内执行 |
| F6 | DC-0064 | `--dry-run` 参数 + `preview()` | 空跑模式 |
| F7 | DC-0060 | `--workspace` 参数 | 指定工作空间 |
| F8 | DC-0061 | REPL 循环 + Session 传递 | 会话内记忆 |
| F10 | DC-0063 扩展 | `REPL._execute_script()` 执行失败流程 | 失败后构造 `ExecutionErrorContext`，进入 `ERROR_RECOVERY` |
| F11 | DC-0067 | `/init` 命令 | Agents.md 持久化会话配置 |
| P2 | DC-0066 | SCRIPT_PREVIEW 确认流程 | 先展后行 |
| P3 | DC-0063 | `cwd=workspace.root` | 最小权限 |
| W1 | DC-0063 | 脚本写入工作空间 | 输出文件放置位置 |
| W2 | DC-0063 | `cwd=workspace.root` | 执行当前目录 |
| W3 | DC-0063 | 工作空间沙箱执行 | 路径隔离 |
| CODE-5 | DC-0063 | 超时 + 异常捕获 | except 不静默吞没 |

---

## 附录：变更记录

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.0.4 | 2026-05-29 | 新增 DC-0071：REPL 新增 `output_fn` property 暴露输出函数；`main()` 启动流程新增 `processor.set_output_fn(repl.output_fn)` 接线步骤；Q&A 回答支持流式逐块输出；§2 新增设计决策、§3.3 更新 REPL 接口、§4.1 更新启动流程 |
| v1.0.3 | 2026-05-28 | DC-0063 扩展：执行失败后不再直接返回 IDLE，而是构造 `ExecutionErrorContext` 并进入 `ERROR_RECOVERY` 状态；REPL 主循环和脚本执行流程图更新；测试策略新增错误恢复场景 |
| v1.0.2 | 2026-05-28 | 新增 `/init` 斜杠命令（DC-0067）：将当前 Session 的任务意图、模板、参数追加写入 Agents.md，支持自动创建文件和边界情况处理 |
| v1.0.1 | 2026-05-28 | REPL 执行结果输出格式改进：成功/失败均展示 stdout + stderr + 返回码 + 耗时；quote_filter Windows 兼容（双引号）；启动时增加 RAG 加载提示避免卡死感 |
| v1.0.0 | 2026-05-26 | 初版，定义 CLI 启动流程、REPL 循环、斜杠命令、用户确认、脚本执行沙箱 |
