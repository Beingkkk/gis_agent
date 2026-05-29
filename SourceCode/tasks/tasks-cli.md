# CLI 层实现任务清单

> 基于 `plan-cli.md` (DC-0060 ~ DC-0066)
> 前置依赖：core 层（T-CORE-01 ~ T-CORE-05）已全部完成
> 更新日期: 2026-05-28

---

## 模块总览

Plan-CLI 实现 GIS Agent 的命令行交互层，是**用户与系统交互的唯一入口**。

| 组件 | 文件 | 职责 | 设计决策 |
|------|------|------|----------|
| `CLIArgs` + `parse_args()` | `cli/args.py` | 启动参数解析 | DC-0060 |
| `ScriptExecutor` | `cli/executor.py` | 脚本执行（subprocess + 超时） | DC-0063, DC-0065 |
| `REPL` | `cli/repl.py` | 交互循环、斜杠命令分发、Y/N确认 | DC-0061, DC-0062, DC-0066 |
| `SlashCommandHandler` | `cli/commands.py` | 斜杠命令处理 | DC-0062 |
| `main()` | `cli/main.py` | 入口函数：初始化链 + REPL 启动 | DC-0060, DC-0061 |

**依赖关系**：
```
main() → parse_args() → load_config() → workspace.initialize()
     → scan_templates() → TemplateRegistry() → ParamValidator() → SessionProcessor()
     → REPL.run()

REPL → SessionProcessor.process() → ScriptExecutor.execute()/preview()
REPL → SlashCommandHandler.handle()
```

---

## T-CLI-01: CLIArgs 参数解析

**设计依据**: plan-cli §3.1, §3.2 (DC-0060)

### 红 — 编写测试

- [ ] `tests/unit/test_cli_args.py`:
  - `test_parse_workspace_flag`: `--workspace /data/gis` → `CLIArgs(workspace=Path("/data/gis"))`
  - `test_parse_config_flag`: `--config /path/to/config.json` → `CLIArgs(config=Path(...))`
  - `test_parse_dry_run_flag`: `--dry-run` → `CLIArgs(dry_run=True)`
  - `test_parse_combined_flags`: `--workspace /data --config cfg.json --dry-run` 全部正确
  - `test_parse_defaults`: 无参数 → `CLIArgs(workspace=None, config=None, dry_run=False)`
  - `test_parse_unknown_flag_errors`: 未知参数 `--foo` → `SystemExit(2)`
  - `test_parse_help_exits`: `--help` → `SystemExit(0)`，输出含 `--workspace`, `--config`, `--dry-run`

### 绿 — 实现代码

- [ ] `cli/args.py`:
  - `CLIArgs(frozen dataclass)`: `workspace: Optional[Path]`, `config: Optional[Path]`, `dry_run: bool`
  - `parse_args(argv: Optional[list[str]] = None) -> CLIArgs`: 使用 `argparse.ArgumentParser`
    - `--workspace`: `type=Path`, `help="工作空间目录路径"`
    - `--config`: `type=Path`, `help="配置文件路径"`
    - `--dry-run`: `action="store_true"`, `help="空跑模式（只展示脚本不执行）"`

### 重构

- [ ] 确认 `cli/__init__.py` 暴露 `CLIArgs`, `parse_args`
- [ ] 确认 help 文本友好，中文或英文统一

**涉及文件**: `cli/args.py`, `cli/__init__.py`, `tests/unit/test_cli_args.py`

---

## T-CLI-02: ScriptExecutor 脚本执行器

**设计依据**: plan-cli §3.4 (DC-0063, DC-0064, DC-0065)

### 红 — 编写测试

- [ ] `tests/unit/test_executor.py`:
  - `test_execute_success`: mock `subprocess.run` 返回 exit 0 → `ExecutionResult(success=True, returncode=0, ...)`
  - `test_execute_failure`: mock 返回 exit 1 + stderr → `success=False`, stderr 被记录
  - `test_execute_timeout`: mock 抛 `subprocess.TimeoutExpired` → 捕获后返回 `success=False`，提示超时
  - `test_execute_cwd_is_workspace`: 验证 `subprocess.run` 被调用时 `cwd=workspace.root`
  - `test_execute_timeout_value`: 验证默认 timeout=300 秒传入
  - `test_preview_prints_script`: `preview()` 打印脚本内容到 stdout，不调用 subprocess
  - `test_execution_result_fields`: `ExecutionResult` 包含 success, returncode, stdout, stderr, duration_ms

### 绿 — 实现代码

- [ ] `cli/executor.py`:
  - `ExecutionResult(frozen dataclass)`: success, returncode, stdout, stderr, duration_ms
  - `ScriptExecutor` 类:
    - `__init__(workspace: Workspace, timeout: int = 300)`
    - `execute(script: RenderedScript) -> ExecutionResult`:
      - 将 `script.content` 写入临时脚本文件（工作空间内）
      - `subprocess.run(cmd=["cmd", "/c", temp_script], cwd=workspace.root, timeout=self._timeout, capture_output=True, text=True)`
      - 计算执行耗时 `duration_ms`
      - 返回 `ExecutionResult`
      - 超时 → 终止进程，返回失败结果
    - `preview(script: RenderedScript) -> None`: 打印脚本内容，不执行

### 重构

- [ ] 确认临时脚本文件在执行后被清理（或保留用于审计，可配置）
- [ ] 确认所有异常路径都记录日志（CODE-5）

**涉及文件**: `cli/executor.py`, `tests/unit/test_executor.py`

---

## T-CLI-03: SlashCommandHandler 斜杠命令处理器

**设计依据**: plan-cli §3.5 (DC-0062)

### 红 — 编写测试

- [ ] `tests/unit/test_cli_commands.py`:
  - `test_quit_command`: `/quit` → 返回退出信号（如 `("QUIT", "再见")`）
  - `test_quit_alias_q`: `/q` → 同上
  - `test_clear_command`: `/clear` → session 重置为 IDLE, history 为空, template=None
  - `test_workspace_command`: `/workspace` → 响应当前工作空间绝对路径
  - `test_templates_command`: `/templates` → 列出可用模板名称列表
  - `test_status_command`: `/status` → 显示当前状态、工作空间路径、历史轮数
  - `test_help_command`: `/help` → 显示所有可用斜杠命令说明
  - `test_unknown_command`: `/foo` → 友好提示未知命令，列出 `/help`
  - `test_command_with_args_ignored`: `/quit now` → 按 `/quit` 处理（忽略多余参数）

### 绿 — 实现代码

- [ ] `cli/commands.py`:
  - `SlashCommandHandler` 类:
    - `COMMANDS: dict[str, callable]` 命令表
    - `handle(command_line: str, session: Session, registry: TemplateRegistry, workspace: Workspace) -> tuple[Session, str, Optional[str]]`:
      - 返回 `(new_session, response_text, action_flag)`
      - `action_flag`: `None` 正常响应, `"QUIT"` 退出信号
    - 各命令处理函数:
      - `_cmd_quit()` → `"再见。"`, action `"QUIT"`
      - `_cmd_clear()` → 重置 session 到 IDLE
      - `_cmd_workspace()` → 返回 `workspace.root`
      - `_cmd_templates()` → 调用 `registry.list_templates()` 格式化输出
      - `_cmd_status()` → 返回状态摘要（state, history长度, template ID）
      - `_cmd_help()` → 返回命令列表和帮助文本

### 重构

- [ ] 确认命令表可扩展（新增命令无需修改 handle 主逻辑）
- [ ] 确认 `cli/__init__.py` 暴露 `SlashCommandHandler`

**涉及文件**: `cli/commands.py`, `cli/__init__.py`, `tests/unit/test_cli_commands.py`

---

## T-CLI-04: REPL 交互循环

**设计依据**: plan-cli §3.3, §4.2, §4.3, §4.4 (DC-0061, DC-0062, DC-0066)

### 红 — 编写测试

- [ ] `tests/unit/test_cli_repl.py`:

**基本循环**:
  - `test_repl_normal_input_passed_to_processor`: 正常输入传递给 `SessionProcessor.process()`
  - `test_repl_prints_response`: processor 返回的响应被打印到 stdout
  - `test_repl_quits_on_slash_quit`: `/quit` 终止循环

**斜杠命令**:
  - `test_repl_clear_resets_session`: `/clear` 后 session 回到 IDLE
  - `test_repl_unknown_command_shows_help`: 未知斜杠命令提示 `/help`

**SCRIPT_PREVIEW 状态 — Y/N 确认**:
  - `test_repl_y_confirms_execution`: 输入 `Y` → 调用 `ScriptExecutor.execute()` → 打印结果 → session 回 IDLE
  - `test_repl_n_cancels_returns_collect`: 输入 `N` → session 回到 PARAM_COLLECT，提示修改参数
  - `test_repl_invalid_confirmation_loops`: 输入 `foo` → 提示"请输入 Y 或 N" → 继续读取
  - `test_repl_empty_confirmation_loops`: 空输入 → 同上
  - `test_repl_execution_failure_shows_stderr`: 执行失败 → 打印 stderr → 提示修复 → session 回 IDLE

**dry-run 模式**:
  - `test_repl_dry_run_skips_execution`: dry_run=True → SCRIPT_PREVIEW 时调用 `preview()` 而非 `execute()` → 提示"dry-run 模式，跳过执行" → session 回 IDLE

**中断处理**:
  - `test_repl_ctrl_c_shows_hint`: `KeyboardInterrupt` → 打印"^C，使用 /quit 退出" → 继续循环
  - `test_repl_ctrl_d_exits`: `EOFError` → 打印"再见" → 正常退出

**Mock 策略（测试中使用）**

- `SessionProcessor`: mock `process()` 返回预设的 `(new_session, response)`
- `ScriptExecutor`: mock `execute()` 返回预设 `ExecutionResult`，mock `preview()` 为 no-op
- `input()`: 用 `unittest.mock.patch("builtins.input")` 预设输入序列
- `sys.stdout`: 用 `io.StringIO` 捕获输出内容

### 绿 — 实现代码

- [ ] `cli/repl.py`:
  - `REPL` 类:
    - `__init__(processor: SessionProcessor, executor: ScriptExecutor, dry_run: bool = False)`
    - `run(session: Session) -> None`: 主循环
      - 打印 `"GIS> "` 提示符
      - `_read_input()`: 读取用户输入，处理 EOF / KeyboardInterrupt
      - 输入以 `"/"` 开头 → `SlashCommandHandler.handle()` → 处理 QUIT 信号
      - 正常输入 → `processor.process()` → 打印 response
      - `new_session.state == SCRIPT_PREVIEW` → `_handle_execution(new_session)`
    - `_handle_execution(session: Session) -> Session`:
      - dry_run=True → `executor.preview()` → 提示"dry-run 跳过执行" → 返回 `with_state(IDLE)`
      - dry_run=False → 打印脚本 → **循环读取 Y/N**
        - `Y`/`y` → `executor.execute()` → 打印结果/错误 → 返回 `with_state(IDLE)`
        - `N`/`n` → 返回 `with_state(PARAM_COLLECT)`，提示"请修改参数"
        - 其他 → 提示"请输入 Y 确认执行，或 N 取消" → 继续循环

### 重构

- [ ] 确认输入输出可注入（便于测试），如 `input_fn` / `output_fn` 参数
- [ ] 确认 `cli/__init__.py` 暴露 `REPL`
- [ ] 确认状态流转与 plan-core 定义的 SCRIPT_PREVIEW 分工一致（core 生成文本，CLI 处理 Y/N）

**涉及文件**: `cli/repl.py`, `cli/__init__.py`, `tests/unit/test_cli_repl.py`

---

## T-CLI-05: main() 入口函数

**设计依据**: plan-cli §3.2, §4.1 (DC-0060, DC-0061)

### 红 — 编写测试

- [ ] `tests/unit/test_cli_main.py`:
  - `test_main_success_path`: 正常启动流程 → REPL.run() 被调用 → 返回 0
  - `test_main_workspace_not_found`: `--workspace /nonexistent` → 打印错误 → 返回 2
  - `test_main_config_not_found`: `--config /nonexistent.json` → 打印错误 → 返回 2
  - `test_main_welcome_message`: 启动时打印欢迎信息，含工作空间路径和可用模板数量
  - `test_main_dry_run_flag_passed`: `--dry-run` → REPL 以 `dry_run=True` 初始化
  - `test_main_builds_session_processor`: 验证 `SessionProcessor` 被正确构建并注入 REPL

**Mock 策略（测试中使用）**

- `parse_args()`: mock 返回预设 `CLIArgs`
- `load_config()`: mock 返回预设 `Config`
- `workspace.initialize()`: mock，部分测试抛 `WorkspaceNotFoundError`
- `scan_templates()`: mock 返回小列表
- `REPL.run()`: mock，避免实际阻塞在输入上
- `sys.exit()`: 捕获退出码

### 绿 — 实现代码

- [ ] `cli/main.py`:
  - `main(argv: Optional[list[str]] = None) -> int`:
    1. `parse_args(argv)` → `CLIArgs`
    2. `load_config(args.config)` → `Config`
    3. `workspace.initialize(workspace_path)` → 失败 → 打印错误 → 返回 2
    4. 定位模板目录：`pkg_root / "data/templates/"`
    5. `scan_templates(template_dir)` → `List[TemplateDef]`
    6. `TemplateRegistry(templates, template_dir)`
    7. `ParamValidator(get_workspace())`
    8. `TemplateEngine(template_dir, get_workspace())`
    9. `LLMClient()`, `PromptBuilder(agents_md)`
    10. `SessionProcessor(registry, validator, template_engine, llm_client, prompt_builder)`
    11. `ScriptExecutor(get_workspace())`
    12. `REPL(processor, executor, dry_run=args.dry_run)`
    13. 打印欢迎信息（含工作空间路径、模板数量、`/help` 提示）
    14. `repl.run(Session())`
    15. 返回 0

### 重构

- [ ] 确认异常处理完整（每个初始化步骤的失败路径）
- [ ] 确认 `sys.exit()` 不在 `main()` 内部调用，以 `return` 码返回（便于测试）
- [ ] 确认 `cli/__main__.py` 调用 `main()`：`sys.exit(main())`

**涉及文件**: `cli/main.py`, `cli/__main__.py`, `tests/unit/test_cli_main.py`

---

## T-CLI-06: 模块入口与包暴露

**设计依据**: plan-cli §3.2 (DC-0060)

### 红 — 编写测试

- [ ] `tests/unit/test_cli_init.py`:
  - `test_cli_module_imports`: `from cli import main, REPL, CLIArgs, parse_args, ScriptExecutor, SlashCommandHandler`
  - `test_cli_main_module_runnable`: `python -m cli --help` 可执行
  - `test_cli_version_info`（如有）: 暴露 `__version__`

### 绿 — 实现代码

- [ ] `cli/__init__.py`: 暴露公共 API
  ```python
  from cli.args import CLIArgs, parse_args
  from cli.commands import SlashCommandHandler
  from cli.executor import ExecutionResult, ScriptExecutor
  from cli.main import main
  from cli.repl import REPL
  ```
- [ ] `cli/__main__.py`:
  ```python
  import sys
  from cli.main import main
  sys.exit(main())
  ```

### 重构

- [ ] 确认不暴露内部模块（如 `cli.commands` 内部函数）
- [ ] 确认 `pyproject.toml` 或 `setup.py` 入口点配置（如有需要）

**涉及文件**: `cli/__init__.py`, `cli/__main__.py`, `tests/unit/test_cli_init.py`

---

## 编码顺序

```
T-CLI-01 (Args) → T-CLI-02 (Executor) → T-CLI-03 (Commands) → T-CLI-04 (REPL) → T-CLI-05 (main) → T-CLI-06 (Init)
```

**原因**：
- Args 和 Executor 无内部依赖，可并行
- Commands 依赖 Session/Registry/Workspace（已存在）
- REPL 依赖 Processor（已存在）+ Executor + Commands
- main() 依赖所有其他组件，必须最后

---

## 质量门禁（每步完成后执行）

- [ ] `ruff format src/ tests/`
- [ ] `ruff check src/ tests/`
- [ ] `mypy --strict src/`
- [ ] `pytest tests/unit/ -v`
- [ ] 覆盖率 ≥ 80%

---

## 需求追溯表

| 需求 ID | 设计决策 | 任务 | 说明 |
|:-------:|:--------:|:----:|------|
| F5 | DC-0066 | T-CLI-04 | Y/N 确认后执行 |
| F5 | DC-0063 | T-CLI-02 | 工作空间内执行（cwd=workspace.root） |
| F6 | DC-0064 | T-CLI-02, T-CLI-04 | dry-run 空跑模式 |
| F7 | DC-0060 | T-CLI-01, T-CLI-05 | `--workspace` 参数 |
| F8 | DC-0061 | T-CLI-04 | REPL 循环保留会话上下文 |
| F10 | DC-0063 | T-CLI-02 | 执行错误信息捕获 |
| F11 | DC-0013 | T-CLI-05 | Agents.md 加载注入 PromptBuilder |
| P2 | DC-0066 | T-CLI-04 | 先展后行（SCRIPT_PREVIEW → Y/N） |
| P3 | DC-0063 | T-CLI-02 | 最小权限（cwd + 临时脚本在工作空间内） |
| W1 | DC-0063 | T-CLI-02 | 脚本写入工作空间 |
| W2 | DC-0063 | T-CLI-02 | cwd=workspace.root |
| CODE-5 | DC-0063 | 全部 | except 不静默吞没 |
| CODE-3 | DC-0031 | T-CLI-05 | LLM 调用封装在 llm/ |

---

## 预估工作量

| 任务 | 复杂度 | 说明 |
|------|:------:|------|
| T-CLI-01 | 低 | argparse 标准库，接口简单 |
| T-CLI-02 | 中 | subprocess mock 策略需仔细设计 |
| T-CLI-03 | 低 | 纯数据转换，无外部依赖 |
| T-CLI-04 | **高** | REPL 是核心交互，状态多、边界场景多 |
| T-CLI-05 | 中 | 初始化链长，但各组件已就绪 |
| T-CLI-06 | 低 | 包结构组装 |
