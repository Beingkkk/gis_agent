# plan-exec-env

| 项目 | 内容 |
|------|------|
| 版本 | v1.1.0 |
| 状态 | DC-0100 已实现，DC-0101~DC-0104 待编码 |
| 作者 | - |
| 日期 | 2026-06-01 |

---

## 1. 设计概述

### 1.1 模块职责

提供 GIS Agent 的 GDAL 脚本执行环境配置与验证能力。负责：

1. **运行时环境配置**：用户在 ExecTab 中动态设置执行环境（shell 类型、conda 环境等），不依赖启动时的静态配置。
2. **Shell 类型管理**：支持 `bash` / `cmd` / `powershell` / `auto` 四种模式，后端自动探测可用 shell。
3. **环境验证**：用户配置后即时验证（探测 shell 存在性、conda 环境有效性、GDAL 可用性）。
4. **脚本执行**：根据配置的 shell 类型生成对应格式的脚本文件（`.sh` / `.bat` / `.ps1`），并使用该环境执行。

本模块是 **api/ 层执行链的独立辅助块**，仅在脚本执行（需要子进程运行环境）前完成环境准备。不影响意图识别、参数收集、模板匹配等其他功能模块。环境配置 UI 嵌入 ExecTab，作为执行前的一个可选设置步骤。

### 1.2 所属架构层次

基础设施层（横切关注点，被 `api/websocket/execute.py` 依赖）。

### 1.3 对应需求项

| 需求 ID | 需求描述 |
|:-------:|---------|
| F4 | 脚本生成：根据模板 + 参数生成 `.bat`/`.sh` 可执行脚本 |
| F5 | 用户确认与执行：进程隔离 |
| P5 | 极简依赖：不引入未经批准的第三方库 |

---

## 2. 设计决策

### DC-0100: 执行环境配置不在 config.json 中，改为运行时设置 ✅ 已实现

**决策**: 移除 `config.json` 中的 `gdal_bin` 字段。执行环境不在启动时配置，而是由用户在 ExecTab 中通过 UI 控件动态设置，绑定到 session 级别。

**实现状态**: 已完成。以下 `gdal_bin` 引用已全部清理：
- `src/config/models.py` — 移除 `gdal_bin: str = ""`
- `src/config/loader.py` — 移除环境变量映射、默认值填充、配置构建
- `src/api/main.py` — Health 端点简化为 `{"status": "ok"}`
- `src/api/websocket/execute.py` — 移除 `gdal_bin` PATH prepend 逻辑
- `frontend/src/api/health.ts` — 移除 `gdal_bin` 字段
- `frontend/src/pages/MainPage.tsx` — 移除 `gdalBin` state 及健康检查
- `frontend/src/components/ExecTab.tsx` — 移除 `gdalBin` prop 及显示
- `tests/unit/test_api_main.py` — 更新断言
- `CLAUDE.md` — 更新描述

**理由**:
- 降低上手门槛：新用户无需先手动编辑配置文件即可开始使用
- 即时反馈：配置后立即验证，用户知道是否可用
- 灵活切换：用户可在不同任务间切换 conda 环境
- **不影响其他功能：环境配置是执行前的独立步骤，与意图识别、参数收集等无关。本模块作为独立块嵌入，仅在脚本执行（子进程运行环境准备）时触发交互**

**替代方案**:
- 保留 `gdal_bin` 在 config.json 中（已否决）：配置繁琐，conda 环境还需要额外环境变量
- 自动探测并静默使用第一个可用环境（已否决）：用户可能不知道用了哪个环境，出错时难以排查

### DC-0101: Shell 类型抽象与自动探测

**决策**: 引入 `ShellType` 枚举（`bash` / `cmd` / `powershell` / `auto`），由 `ShellDetector` 根据平台自动探测可用 shell。探测优先级：

**Windows 平台**:
1. Git Bash（`C:/Program Files/Git/bin/bash.exe`）
2. conda 内置 bash（`{conda_root}/Library/bin/bash.exe`）
3. cmd（系统内置）
4. PowerShell（系统内置）

**类 Unix 平台（Linux/macOS）**:
1. bash（`/bin/bash`）
2. sh（`/bin/sh`，兜底）

**探测逻辑**:
```
shell = config.shell
if shell == "auto":
    shell = detect_by_platform()
verify_shell_executable(shell, config.shell_path)
```

**理由**:
- bash 的 `set -e` 让任何命令失败立即退出并正确传递 return code
- bash 支持管道、进程替换、多行逻辑，复杂 GDAL 工作流必需
- `auto` 模式减少用户配置负担

### DC-0102: Conda 环境变量推导（不依赖 conda CLI）

**决策**: conda 环境不通过 `conda activate` 或 `conda run` 激活，而是根据 conda 安装路径直接推导环境变量。

**推导规则**:
```
已知：conda env 路径 = {conda_root}/envs/{env_name}

PATH      ← prepend {env_path}/Library/bin
GDAL_DATA ← {env_path}/Library/share/gdal
PROJ_DATA ← {env_path}/Library/share/proj
PROJ_LIB  ← {env_path}/Library/share/proj
```

**conda 安装位置探测**（按优先级）:
1. 环境变量 `CONDA_PREFIX`（当前激活的 conda base）
2. 环境变量 `CONDA_ROOT`
3. 常见路径（Windows）: `C:/ProgramData/anaconda3`, `C:/Users/{user}/.conda`
4. 常见路径（macOS/Linux）: `~/anaconda3`, `~/miniconda3`, `/opt/conda`

**验证**: 组装环境变量后，执行 `ogr2ogr --version` 验证 GDAL 可用性（5秒超时）。

**理由**:
- `conda activate` 在子进程中不可靠（依赖 shell hook）
- `conda run` 需要 conda CLI 在 PATH 中，且增加进程包装层
- conda 环境内部路径结构稳定，直接推导更可控
- 零额外依赖（符合 P5）

### DC-0103: 多 shell 脚本格式

**决策**: 根据 `shell` 类型生成对应格式的脚本文件，确保语法正确、错误码可传递。

| Shell | 文件后缀 | 头部 | 错误处理 |
|-------|---------|------|---------|
| bash | `.sh` | `#!/bin/bash` | `set -euo pipefail` |
| cmd | `.bat` | `@echo off` | `if errorlevel 1 exit /b 1` |
| powershell | `.ps1` | `#Requires -Version 5.1` | `$ErrorActionPreference = "Stop"` |

**理由**:
- 不同 shell 的错误码传递机制不同
- `set -euo pipefail` 是 bash "严格模式"，管道中任何命令失败都导致整体非零退出

### DC-0104: Session 级环境绑定

**决策**: 用户配置的执行环境绑定到 `Session` 对象，随会话生命周期存在。不持久化到 config.json。

### DC-0105: 脚本执行临时化，导出与执行分离

**决策**: 脚本执行时的临时文件不再写入工作空间，改为写入项目根目录下的 `cache/` 子目录（自动创建）。用户如需保存脚本，通过独立的"导出脚本"功能主动保存。

**执行流程变更**:
- 旧：`write_script(commands, workspace)` → `{workspace}/script_{uuid}.{ext}`
- 新：`write_script_to_temp(commands)` → `{project_root}/cache/script_{uuid}.{ext}`，执行后清理

**导出流程**（独立功能）:
```
用户点击"导出脚本"
    │
    ▼
IPC saveFile(dialog) → 用户选择保存路径
    │
    ▼
POST /session/{id}/export-script {output_path}
    │
    ▼
后端渲染脚本 → write_script(commands, output_path)
    │
    ▼
返回 {success, path, size}
```

**默认导出文件名**: `script_{template_id}_{timestamp}.{ext}`（ext 根据 shell 类型：`.bat` / `.sh` / `.ps1`）

**理由**:
- 工作空间不再被临时脚本文件污染，保持干净
- 用户有明确的"保存脚本"意图时才生成持久化文件
- 导出操作不影响会话状态，纯副作用操作
- `cache/` 目录位于项目根目录下，路径可控、易排查，避免 Windows 系统 Temp 目录（`C:\Users\...\AppData\Local\Temp`）带来的跨盘/权限问题

**依赖关系**:
- plan-ux DC-UX-11a（前端导出按钮 UX）依赖本决策
- plan-electron 新增 `saveFile` IPC（导出时保存对话框）

**流程**:
```
用户在前端设置环境 → POST /session/{id}/exec-env → 后端验证 → 保存到 session
                                                            │
                                                            ▼
执行脚本时：session.exec_env ?? 系统默认环境（os.environ + PATH）
```

**理由**:
- 会话级绑定：不同任务可使用不同 conda 环境
- 不持久化：简化实现，避免配置文件读写权限问题
- 回退安全：未配置时直接使用系统环境，不影响基本功能

---

## 3. 接口定义

### 3.1 数据模型

```python
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


class ExecEnvType(Enum):
    """执行环境类型。"""
    SYSTEM = "system"       # 直接使用系统 PATH（默认）
    CONDA = "conda"         # conda 环境，自动推导 GDAL 数据路径


class ShellType(Enum):
    """Shell 类型。"""
    BASH = "bash"
    CMD = "cmd"
    POWERSHELL = "powershell"


@dataclass(frozen=True)
class ExecEnvConfig:
    """执行环境配置（用户通过 UI 设置）。

    Design:
        DC-0100
    """
    type: ExecEnvType = ExecEnvType.SYSTEM
    env_name: str = ""              # conda 环境名（type=CONDA 时有效）
    shell: str = "auto"             # "auto" / "bash" / "cmd" / "powershell"
    shell_path: str = ""            # shell 绝对路径（可选，覆盖自动探测）


@dataclass(frozen=True)
class ExecEnvironment:
    """已解析的执行环境（可直接用于 subprocess）。

    Design:
        DC-0102
    """
    env_vars: Dict[str, str]        # 完整环境变量字典
    shell: ShellType                # 解析后的 shell 类型
    shell_executable: Path          # shell 可执行文件绝对路径
    gdal_available: bool            # GDAL 验证结果
    gdal_version: str = ""          # ogr2ogr --version 输出
```

### 3.2 Session 模型扩展

```python
# src/core/models.py — Session dataclass

@dataclass(frozen=True)
class Session:
    """会话上下文（扩展后）。"""
    state: SessionState = SessionState.IDLE
    history: List[Message] = field(default_factory=list)
    template: Optional[TemplateDef] = None
    params: Dict[str, str] = field(default_factory=dict)
    candidates: List[TemplateDef] = field(default_factory=list)
    error_context: Optional[ExecutionErrorContext] = None
    user_script: Optional[str] = None
    exec_env: Optional[ExecEnvironment] = None  # 新增（DC-0104）

    def with_exec_env(self, exec_env: Optional[ExecEnvironment]) -> "Session":
        """设置执行环境。"""
        return Session(
            state=self.state,
            history=self.history,
            template=self.template,
            params=self.params,
            candidates=self.candidates,
            error_context=self.error_context,
            user_script=self.user_script,
            exec_env=exec_env,
        )
```

### 3.3 公共 API

```python
class ShellDetector:
    """Shell 可用性探测。

    Design:
        DC-0101
    """

    @staticmethod
    def detect() -> tuple[ShellType, Path]:
        """自动探测当前平台最优可用 shell。

        Returns:
            (shell_type, shell_executable_path)

        Raises:
            RuntimeError: 无任何可用 shell。
        """

    @staticmethod
    def verify(shell: ShellType, custom_path: Optional[Path] = None) -> Path:
        """验证指定 shell 是否可执行。"""


class CondaEnvDetector:
    """Conda 环境路径探测。

    Design:
        DC-0102
    """

    @staticmethod
    def find_conda_root() -> Optional[Path]:
        """探测 conda 安装根目录。"""

    @staticmethod
    def resolve_env_path(env_name: str) -> Optional[Path]:
        """根据环境名解析 conda 环境绝对路径。"""

    @staticmethod
    def build_env_vars(env_path: Path) -> Dict[str, str]:
        """根据 conda 环境路径推导 GDAL 相关环境变量。"""

    @staticmethod
    def list_envs() -> List[str]:
        """列出所有已安装的 conda 环境名。

        读取 {conda_root}/envs/ 目录下的子目录名。
        """


class EnvironmentBuilder:
    """执行环境构建器。

    Design:
        DC-0100, DC-0102
    """

    def __init__(self, config: ExecEnvConfig) -> None:
        """Args:
            config: 执行环境配置。
        """

    def build(self) -> ExecEnvironment:
        """构建完整执行环境。

        1. 解析 shell 类型（auto → 探测）
        2. 验证 shell 可执行性
        3. 根据 type 组装环境变量（system / conda）
        4. 验证 GDAL 可用性（ogr2ogr --version，5秒超时）

        Returns:
            完整的执行环境对象。

        Raises:
            RuntimeError: shell 不可用。
            FileNotFoundError: conda 环境不存在。
        """


class ShellExecutor:
    """Shell 执行器。

    Design:
        DC-0101, DC-0103
    """

    def __init__(self, env: ExecEnvironment) -> None:
        """Args:
            env: 已构建的执行环境。
        """

    def write_script(self, commands: List[str], output_path: Path) -> Path:
        """将命令列表写入指定路径的脚本文件。

        Args:
            commands: 命令行列表。
            output_path: 目标文件完整路径（含文件名和后缀）。

        Returns:
            写入的文件路径。

        Design:
            DC-0103, DC-0105
        """

    def write_script_to_temp(self, commands: List[str]) -> Path:
        """将命令列表写入系统临时目录的脚本文件，供执行使用。

        文件名格式：script_{timestamp}_{uuid}.{ext}
        执行完成后由调用方负责清理。

        Returns:
            临时脚本文件路径。

        Design:
            DC-0105
        """

    async def execute(
        self,
        script_path: Path,
        cwd: Path,
        timeout: int = 300,
    ) -> asyncio.subprocess.Process:
        """启动脚本执行子进程。"""
```

### 3.4 新增 API 端点

```python
# api/routes/exec_env.py (新建)

from fastapi import APIRouter, Depends

router = APIRouter()


@router.post("/exec-env/verify")
async def verify_exec_env(
    request: ExecEnvVerifyRequest,
) -> ExecEnvVerifyResponse:
    """验证执行环境配置。

    接收用户填写的环境配置，返回验证结果。
    不修改任何 session 状态，纯验证接口。

    Request:
        {"type": "conda", "env_name": "gis-agent", "shell": "bash"}

    Response:
        {
            "valid": true,
            "shell": {"type": "bash", "path": "C:/Program Files/Git/bin/bash.exe"},
            "gdal": {"available": true, "version": "GDAL 3.9.0..."},
            "env_vars": {"GDAL_DATA": "...", "PROJ_DATA": "..."},
            "error": null
        }
    """


@router.post("/session/{session_id}/exec-env")
async def set_session_exec_env(
    session_id: str,
    request: ExecEnvSetRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> SessionResponse:
    """将执行环境配置保存到 session。

    先调用 EnvironmentBuilder.build() 验证，验证通过后保存到 session.exec_env。
    """
```

### 3.5 Health 端点（简化）

```python
# api/main.py

@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}
```

---

## 4. 数据流与控制流

### 4.1 环境配置流程（运行时，仅在需要子进程执行时触发）

> **触发时机**: 本流程独立于主业务流。仅在用户进入 ExecTab 且即将执行脚本（需要子进程运行环境）时，才展示环境配置入口。意图识别、参数收集、模板发现等阶段完全不涉及本模块。

```
[用户在 ExecTab 准备执行脚本，点击"环境设置"]
    │
    ▼
展开环境配置面板（独立控件，不影响命令预览/参数摘要/执行按钮）
    │
    ├──→ 选择 shell 类型（bash/cmd/powershell/auto）
    ├──→ 选择环境类型（system / conda）
    │       └── conda → 输入/选择环境名
    │
    ▼
[点击"测试环境"]
    │
    ▼
POST /exec-env/verify
    │
    ├──→ EnvironmentBuilder.build()
    │       ├──→ ShellDetector.detect() / verify()
    │       ├──→ CondaEnvDetector.find_conda_root()（如 type=conda）
    │       ├──→ CondaEnvDetector.build_env_vars()
    │       └──→ 验证 ogr2ogr --version（5秒超时）
    │
    ▼
返回验证结果 → 前端显示状态（✓ / ✗ + 详细信息）
    │
    ▼
[点击"保存"]
    │
    ▼
POST /session/{id}/exec-env
    │
    ├──→ 再次验证
    └──→ session.with_exec_env(env) → 保存
    │
    ▼
执行时使用 session.exec_env
```

### 4.2 脚本执行流程（更新后）

```
[SCRIPT_PREVIEW 状态]
    │
    ▼
获取 ExecEnvironment
    ├──→ session.exec_env（用户配置）
    └──→ 回退：系统默认（os.environ）
    │
    ▼
ShellExecutor.write_script_to_temp(commands)
    │
    ├──→ bash → 生成 {project_root}/cache/script_{uuid}.sh
    ├──→ cmd  → 生成 {project_root}/cache/script_{uuid}.bat
    └──→ powershell → 生成 {project_root}/cache/script_{uuid}.ps1
    │
    ▼
ShellExecutor.execute(script_path, cwd=workspace)
    │
    ├──→ bash → subprocess_exec(bash, script_path, env=..., cwd=...)
    ├──→ cmd  → subprocess_exec(cmd, "/c", script_path, env=..., cwd=...)
    └──→ powershell → subprocess_exec(powershell, "-File", script_path, ...)
    │
    ▼
执行完成后清理临时脚本文件
```

**设计说明**（DC-0105）：
- 执行时的临时脚本写入项目根目录 `cache/` 子目录（自动创建），不再污染工作空间
- 临时文件由 `execute` 调用方在执行完成后负责清理
- 用户如需保留脚本，使用独立的"导出脚本"功能（DC-UX-11a）

---

## 5. 依赖关系

### 5.1 向上依赖

| 模块 | 接口 | 用途 |
|------|------|------|
| 项目根目录 `cache/` | — | 脚本执行时临时文件写入目录（DC-0105） |

### 5.2 向下暴露

| 接口 | 使用方 |
|------|--------|
| `EnvironmentBuilder.build()` | `api/routes/exec_env.py`（verify 端点） |
| `ShellExecutor.write_script()` | `api/routes/session.py`（导出脚本） |
| `ShellExecutor.write_script_to_temp()` | `api/websocket/execute.py`（执行时临时脚本） |
| `ShellExecutor.execute()` | `api/websocket/execute.py`（启动子进程） |
| `CondaEnvDetector.list_envs()` | `api/routes/exec_env.py`（下拉列表） |

---

## 6. 异常与错误处理

| 异常类型 | 触发条件 | 处理策略 |
|---------|---------|---------|
| `FileNotFoundError` | 配置的 `shell_path` 不存在 | verify 端点返回 `valid: false` + 错误信息 |
| `RuntimeError` | `ShellDetector.detect()` 无任何可用 shell | 同上 |
| `FileNotFoundError` | conda 环境路径不存在 | 同上，提示检查 `env_name` |
| `subprocess.TimeoutExpired` | `ogr2ogr --version` 验证超时（5秒） | `gdal_available: false`，提示检查环境 |
| `subprocess.CalledProcessError` | `ogr2ogr --version` 返回非零码 | 同上 |

---

## 7. 测试策略

### 7.1 单元测试覆盖

| 测试场景 | 验证点 |
|---------|--------|
| ShellDetector — Windows 探测 bash | Git Bash 存在时返回 BASH |
| ShellDetector — Windows 回退 cmd | 无 Git Bash 时返回 CMD |
| ShellDetector — Linux 探测 bash | `/bin/bash` 存在时返回 BASH |
| ShellDetector — 无可用 shell | 抛出 RuntimeError |
| CondaEnvDetector — 通过 CONDA_PREFIX | 正确解析 conda 根目录 |
| CondaEnvDetector — build_env_vars | 正确推导 PATH / GDAL_DATA / PROJ_DATA / PROJ_LIB |
| CondaEnvDetector — list_envs | 返回 envs/ 目录下的环境名列表 |
| EnvironmentBuilder — system 类型 | 仅使用系统 PATH，验证 GDAL 可用性 |
| EnvironmentBuilder — conda 类型 | 推导完整环境变量，验证 GDAL 可用性 |
| EnvironmentBuilder — auto shell | 自动探测并解析为具体 shell 类型 |
| ShellExecutor — write_script (bash) | 生成 `.sh` 文件到指定路径，包含 `set -euo pipefail` |
| ShellExecutor — write_script (cmd) | 生成 `.bat` 文件到指定路径，包含 `@echo off` |
| ShellExecutor — write_script_to_temp | 生成到项目根目录 cache/ 子目录，文件名含 uuid |
| verify 端点 — 有效配置 | 返回 `valid: true` + shell/gdal 信息 |
| 导出脚本端点 — 成功 | 按 shell 类型生成正确格式，写入用户指定路径 |
| 导出脚本端点 — 路径不可写 | 返回 400 + 错误信息 |
| verify 端点 — 无效 shell | 返回 `valid: false` + 错误信息 |
| verify 端点 — 无效 conda 环境 | 返回 `valid: false` + 环境不存在 |
| session exec-env 端点 — 保存成功 | session.exec_env 正确更新 |
| session exec-env 端点 — 验证失败 | 返回 400 + 错误信息，session 不变 |

### 7.2 Mock 策略

- `Path.exists()` / `Path.is_file()`: monkeypatch 模拟 shell 可执行文件存在/不存在
- `subprocess.run`: mock `ogr2ogr --version` 的成功/失败/超时
- `os.environ`: 使用 `monkeypatch.setenv()` 模拟 `CONDA_PREFIX`
- 临时目录: `tmp_path` fixture 用于脚本文件写入测试

---

## 8. 需求追溯表

| 需求 ID | 设计决策 | 代码文件/函数 | 说明 |
|:-------:|:--------:|:-------------:|------|
| F4 | DC-0103 | `ShellExecutor.write_script()` | 根据 shell 类型生成 `.sh`/`.bat`/`.ps1` |
| F5 | DC-0101, DC-0102 | `ShellExecutor.execute()`, `EnvironmentBuilder.build()` | 进程隔离、环境变量准备 |
| P5 | DC-0102 | `CondaEnvDetector`（纯 Python） | 不引入 `conda` 库等额外依赖 |
| — | DC-0100 | `api/routes/exec_env.py` | 运行时环境配置，不依赖 config.json |
| — | DC-0104 | `Session.exec_env`, `with_exec_env()` | 会话级环境绑定 |
| — | DC-0105 | `ShellExecutor.write_script_to_temp()`, `POST /session/{id}/export-script` | 执行临时化，导出与执行分离 |

---

## 附录：变更记录

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.3.0 | 2026-06-02 | **临时目录改为项目 cache/**：DC-0105 更新，临时脚本从 `tempfile.gettempdir()`（Windows 系统 Temp）改为项目根目录 `./cache/`（自动创建），避免跨盘路径问题和权限困扰；同步更新 `cli/executor.py` |
| v1.2.0 | 2026-06-02 | **脚本执行临时化 + 导出分离**：新增 DC-0105；`ShellExecutor.write_script()` 改为接受任意 `output_path`；新增 `write_script_to_temp()` 用于执行时临时文件；执行流程从 workspace 改为 temp 目录；新增 `/session/{id}/export-script` API；更新 §5.2 向下暴露表 |
| v1.1.0 | 2026-06-01 | DC-0100 标记为已实现。明确模块定位：独立块，仅在子进程执行时触发交互，不影响其他功能模块 |
| v1.0.0 | 2026-06-01 | 初版。移除 config.json 中的 `gdal_bin` 配置；改为运行时通过 UI 设置执行环境；定义 ShellDetector、CondaEnvDetector、ShellExecutor、EnvironmentBuilder；新增 `/exec-env/verify` 和 `/session/{id}/exec-env` API；Session 新增 `exec_env` 字段 |
