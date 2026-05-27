# tasks-workspace

| 项目 | 内容 |
|------|------|
| 关联 Plan | `plan-workspace.md` v2.0.0 |
| 对应模块 | `core/workspace.py` |
| 状态 | 待执行 |

---

## 任务总览

本模块采用 **TDD（测试先行）** 方式实现。全部任务严格遵循红-绿-重构循环：

```
W-01 ~ W-02: 红阶段 —— 提交全部失败测试骨架
W-03 ~ W-11: 绿阶段 —— 逐个实现使测试通过
W-12: 重构阶段 —— 代码质量检查与优化
```

---

## Phase 1: 红 —— 失败测试骨架（必须先于实现提交）

### W-01: 创建 `src/core/__init__.py` 和 `src/core/workspace.py` 空模块

- 创建 `SourceCode/src/core/__init__.py`（空文件或仅注释）
- 创建 `SourceCode/src/core/workspace.py`，仅包含异常类型和 `Workspace` 类骨架（`pass`）
- 不实现任何方法体
- **此步骤使测试可导入被测模块**

### W-02: 创建 `tests/unit/test_workspace.py` —— 全部失败测试

依据 `plan-workspace.md` §7.1 测试策略，编写全部测试函数，每个测试直接调用尚未实现的方法，**预期失败**。

测试清单（需全部覆盖）：

| # | 测试函数名 | 验证场景 | 预期失败原因 |
|---|-----------|---------|-------------|
| 1 | `test_workspace_init_with_valid_path` | 正常初始化 | `Workspace.__init__` 未实现 |
| 2 | `test_workspace_init_with_relative_path` | 相对路径初始化 | `resolve()` 未处理 |
| 3 | `test_workspace_init_nonexistent_dir` | 不存在目录 → WorkspaceNotFoundError | 异常未抛出 |
| 4 | `test_workspace_init_file_as_path` | 文件作为路径 → WorkspaceNotFoundError | 同上 |
| 5 | `test_root_property_returns_absolute_path` | root 属性返回 Path | 属性未实现 |
| 6 | `test_resolve_path_relative` | 相对路径 → workspace 基准 | `resolve_path` 未实现 |
| 7 | `test_resolve_path_absolute` | 绝对路径 → 直通不拦截 | 同上 |
| 8 | `test_resolve_path_must_exist_when_exists` | must_exist=True 且存在 | 同上 |
| 9 | `test_resolve_path_must_exist_when_missing` | must_exist=True 不存在 → PathNotFoundError | 异常未抛出 |
| 10 | `test_generate_output_path_with_timestamp` | 默认附加时间戳 | `generate_output_path` 未实现 |
| 11 | `test_generate_output_path_without_timestamp` | timestamp=False 不附加 | 同上 |
| 12 | `test_generate_output_path_absolute_base` | 绝对路径基准直接使用 | 同上 |
| 13 | `test_generate_output_path_preserves_subdir` | 子目录结构保留 | 同上 |
| 14 | `test_load_agents_md_exists` | Agents.md 存在 → AgentsMdContent | `load_agents_md` 未实现 |
| 15 | `test_load_agents_md_not_exists` | Agents.md 不存在 → None | 同上 |
| 16 | `test_load_agents_md_permission_error` | 权限问题 → WorkspaceError | 同上 |
| 17 | `test_get_cwd_returns_root` | get_cwd 返回 workspace.root | `get_cwd` 未实现 |
| 18 | `test_initialize_creates_singleton` | initialize 创建单例 | `initialize` 未实现 |
| 19 | `test_get_workspace_before_initialize` | 未初始化 → RuntimeError | 异常未抛出 |
| 20 | `test_workspace_instance_is_immutable` | Session/dataclass 式不可变性验证 | 属性可写 |

**提交要求**：`test_workspace.py` 中的测试全部 import 成功、运行失败。这是进入编码阶段的第一笔代码。

---

## Phase 2: 绿 —— 逐个实现使测试通过

### W-03: 实现异常类型

- `WorkspaceError(Exception)`
- `WorkspaceNotFoundError(WorkspaceError)`
- `PathNotFoundError(WorkspaceError)`

设计决策：DC-0010（v2.0.0 移除 PathEscapeError）

### W-04: 实现 `Workspace.__init__()` 和 `Workspace.root`

- 接收 `Path`，调用 `resolve()` 转为绝对路径
- 校验路径存在且是目录，否则抛 `WorkspaceNotFoundError`
- `root` 以 `@property` 暴露

设计决策：DC-0010, DC-0014

### W-05: 实现 `Workspace.resolve_path()`

- 判断输入是绝对路径还是相对路径
- 相对路径 → 以 `self.root` 为基准拼接 → `resolve()`
- 绝对路径 → 直接 `resolve()`
- `must_exist=True` 时检查存在性，不存在抛 `PathNotFoundError`
- **不限制范围**——v2.0.0 核心变更

设计决策：DC-0011（v2.0.0 新语义）

### W-06: 实现 `Workspace.generate_output_path()`

- 解析用户输入路径（同 `resolve_path` 逻辑）
- `timestamp=True`（默认）：附加 `%Y%m%d_%H%M%S` 时间戳
- `timestamp=False`：不附加时间戳
- 保留子目录结构
- 返回 `Path`

设计决策：DC-0012

### W-07: 实现 `Workspace.load_agents_md()`

- 检查 `self.root / "Agents.md"` 是否存在
- 存在 → 读取全文 → 返回 `AgentsMdContent(content, path)`
- 不存在 → 返回 `None`
- 读取失败（权限等）→ 抛 `WorkspaceError`

设计决策：DC-0013

### W-08: 实现 `Workspace.get_cwd()`

- 直接返回 `self.root`

设计决策：DC-0010

### W-09: 实现模块级单例函数 `initialize()` 和 `get_workspace()`

- 模块级私有变量 `_workspace_instance: Optional[Workspace] = None`
- `initialize(root)` → 创建 `Workspace(root)` → 存入单例 → 返回
- `get_workspace()` → 若单例未初始化抛 `RuntimeError`，否则返回
- 提供 `_reset_singleton()` 测试辅助函数（不暴露为公开 API）

设计决策：DC-0014

### W-10: 实现 `src/core/__init__.py` 公开 API

导出：
- `Workspace`
- `AgentsMdContent`
- `WorkspaceError`, `WorkspaceNotFoundError`, `PathNotFoundError`
- `initialize`, `get_workspace`

### W-11: 运行全部测试，逐一修复失败

逐条运行 `pytest tests/unit/test_workspace.py -v`，确保全部通过。如有失败，定位原因并修复（实现代码或测试期望）。

---

## Phase 3: 重构与质量检查

### W-12: 代码质量门禁

```bash
cd SourceCode
export PYTHONPATH=src

ruff format src/core/ tests/unit/test_workspace.py
ruff check src/core/ tests/unit/test_workspace.py
mypy --strict src/core/
pytest tests/unit/test_workspace.py -v
```

全部通过后方可标记本模块完成。

---

## 任务-设计决策追溯

| 任务 ID | 覆盖的设计决策 | 说明 |
|:-------:|:-------------:|------|
| W-03 | DC-0010 | 异常类型定义 |
| W-04 | DC-0010, DC-0014 | Workspace 初始化 |
| W-05 | DC-0011 (v2.0.0) | 路径规范化（无边界限制） |
| W-06 | DC-0012 | 时间戳防覆盖 |
| W-07 | DC-0013 | Agents.md 加载 |
| W-08 | DC-0010 | 默认 cwd |
| W-09 | DC-0014 | 全局单例 |
| W-10 | — | 模块公开 API |
| W-11 ~ W-12 | — | 测试通过 + 质量检查 |

---

## 附录：与其他模块的衔接

| 接口 | 使用方 | 备注 |
|------|--------|------|
| `Workspace.resolve_path()` | `templates/` (safe_path 过滤器) | 仅做规范化，不限制范围 |
| `Workspace.generate_output_path()` | `templates/` (脚本输出路径) | 时间戳防覆盖 |
| `Workspace.load_agents_md()` | `llm/PromptBuilder` | 注入系统提示词 |
| `Workspace.get_cwd()` | `cli/ScriptExecutor` | 脚本执行默认 cwd |
| `initialize()` / `get_workspace()` | `cli/main.py` | 启动时初始化 |
