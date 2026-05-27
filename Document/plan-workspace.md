# plan-workspace

| 项目 | 内容 |
|------|------|
| 版本 | v2.0.0 |
| 状态 | 设计基线 |
| 作者 | - |
| 日期 | 2026-05-27 |

---

## 1. 设计概述

### 1.1 模块职责

管理 GIS Agent 的项目锚点与默认操作上下文：工作空间的初始化与规范化、`Agents.md` 长期记忆的自动加载、路径规范化辅助、输出文件名防覆盖。本模块是**项目记忆的入口**（F11），同时作为脚本执行的默认当前目录（W2）。

> **设计定位说明**：GIS 数据通常体积大且分散在多个目录，强制将数据集中在单一工作空间内不现实。因此本模块**不限制**文件操作必须在 workspace 内——数据路径可以是任意合法路径。工作空间的核心意义是存放 `Agents.md`，为 Agent 提供项目级长期记忆和默认上下文。

### 1.2 所属架构层次

核心层（`core/`）。被 CLI 层和模板引擎依赖，不直接依赖上层模块。

### 1.3 对应需求项

| 需求 ID | 需求描述 |
|:-------:|---------|
| F7 | 支持 `--workspace` 参数；作为默认 cwd 和 Agents.md 探测位置 |
| F11 | 自动读取工作空间下的 `Agents.md` 注入系统提示词 |
| W1 | 生成脚本和输出文件**默认**放置在工作空间下（可覆盖） |
| W2 | 脚本执行时，将工作空间作为进程的默认当前目录（cwd） |

---

## 2. 设计决策

### DC-0010: 工作空间以绝对路径的 `pathlib.Path` 对象管理

**决策**: 工作空间根目录在初始化时即转换为绝对路径并规范化（`resolve()`），内部始终以 `Path` 对象传递，禁止字符串拼接。

**理由**:
- `pathlib.Path` 跨平台（Windows / Linux / macOS），消除 `\`/`/` 差异
- `resolve()` 消除符号链接和 `.` / `..` 组件，使路径比较可靠
- 与 CODE-2（禁止 `os.path.join` 处理用户输入路径）完全一致

### ~~DC-0011: 路径安全校验采用"解析后前缀匹配"策略~~ → DC-0011: 路径规范化提供统一的绝对路径解析

**决策（v2.0.0 变更）**: 不再将工作空间作为安全边界限制文件访问范围。`resolve_path()` 仅负责将用户输入（相对或绝对路径）解析为**规范化后的绝对路径**，不做范围限制。GIS 数据天然分散，用户应能操作任意合法路径。

**理由**:
- GIS 原始数据体积大，通常存储在专用目录，不可能全部复制到工作空间
- 输出路径也应灵活指定，不应强制在工作空间内
- "工作空间"的定位改为"项目记忆锚点"而非"安全沙箱"
- 路径规范化（消除 `.`/`..`/符号链接）仍然必要，确保路径可预测

**保留的安全底线**:
- 相对路径以工作空间根为基准解析（如用户输入 `data/roads.shp` → `workspace/data/roads.shp`）
- 绝对路径直接使用（如 `D:\gis\roads.shp` → 不变）
- 不拦截合法的外部路径访问

### DC-0012: 输出文件默认附加时间戳防覆盖

**决策**: 所有生成的输出文件（脚本、处理结果）默认在基础文件名后附加时间戳，除非用户显式指定覆盖。

**理由**:
- 防止批量处理时前一轮结果被静默覆盖
- 时间戳保留操作历史，便于回溯

**时间戳格式**: `%Y%m%d_%H%M%S`（如 `roads_20260526_143052.json`）

### DC-0013: Agents.md 在工作空间根目录自动探测

**决策**: 每次设置/切换工作空间时，自动检测根目录下是否存在 `Agents.md`，若存在则加载其全文内容。

**理由**:
- 符合 F11 的无感加载要求
- 与项目级配置解耦，每个工作空间可有自己的记忆
- 失败静默：文件不存在时不报错，返回 `None`

### DC-0014: Workspace 类采用进程级单例

**决策**: `Workspace` 实例在进程内唯一，通过 `get_workspace()` 全局访问。

**理由**:
- 避免将 workspace 路径在各层函数间层层传递
- 配置逻辑集中在一处，无分散风险
- CLI 启动时初始化一次，运行期不变

---

## 3. 接口定义

### 3.1 异常类型

```python
class WorkspaceError(Exception):
    """工作空间模块的基础异常。"""


class WorkspaceNotFoundError(WorkspaceError):
    """工作空间目录不存在或不可读。"""


class PathNotFoundError(WorkspaceError):
    """用户提供的相对路径在预期位置不存在（用于输入文件校验，非安全拦截）。"""
```

> **注**: v2.0.0 移除了 `PathEscapeError`。工作空间不再作为安全边界，因此不存在"路径逃逸"概念。路径合法性由操作系统和 GDAL 运行时处理。

### 3.2 Workspace 类

```python
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class AgentsMdContent:
    """Agents.md 加载结果。"""
    content: str
    path: Path


class Workspace:
    """工作空间管理器。

    提供路径规范化、输出文件名生成、Agents.md 加载。
    进程内单例，通过 initialize() / get_workspace() 访问。

    Design:
        DC-0010, DC-0011, DC-0012, DC-0013, DC-0014
    """

    def __init__(self, root: Path) -> None:
        """初始化工作空间。

        Args:
            root: 工作空间根目录路径。会被 resolve() 为绝对路径。

        Raises:
            WorkspaceNotFoundError: 目录不存在或不是目录。
        """

    @property
    def root(self) -> Path:
        """工作空间根目录（绝对路径）。"""

    def resolve_path(self, user_input: str, must_exist: bool = False) -> Path:
        """将用户输入的路径解析为规范化后的绝对路径。

        1. 若 user_input 为绝对路径，直接 resolve()
        2. 若 user_input 为相对路径，以 workspace.root 为基准拼接后 resolve()
        3. 若 must_exist=True，校验文件/目录是否存在（仅作提示，不拦截）

        Args:
            user_input: 用户提供的路径（相对或绝对，如 "data/roads.shp"
                       或 "D:\\gis\\roads.shp"）。
            must_exist: 是否要求路径已存在（用于输入文件校验，友好提示）。

        Returns:
            规范化后的绝对路径。

        Raises:
            PathNotFoundError: must_exist=True 且路径不存在。
        """

    def generate_output_path(self, user_input: str, ext: str,
                             timestamp: bool = True) -> Path:
        """生成输出文件路径，可选附加时间戳防覆盖。

        Args:
            user_input: 用户指定的基础文件名（可含子目录，不含扩展名）。
            ext: 扩展名（如 ".json"、".bat"）。
            timestamp: 是否附加时间戳。默认 True。

        Returns:
            规范化后的绝对输出路径。
            若 user_input 为相对路径，以 workspace.root 为基准；
            若为绝对路径，直接使用。
        """

    def load_agents_md(self) -> Optional[AgentsMdContent]:
        """加载工作空间根目录下的 Agents.md。

        Returns:
            AgentsMdContent 对象，若文件不存在则返回 None。

        Raises:
            WorkspaceError: 文件存在但读取失败（权限问题等）。
        """

    def get_cwd(self) -> Path:
        """返回工作空间根目录，作为脚本执行的默认 cwd。"""
```

### 3.3 模块级函数

```python
def initialize(root: Path) -> Workspace:
    """初始化全局 Workspace 单例。

    Args:
        root: 工作空间根目录。

    Returns:
        Workspace 实例。
    """


def get_workspace() -> Workspace:
    """获取已初始化的 Workspace 单例。

    Raises:
        RuntimeError: 在 initialize() 之前调用。
    """
```

---

## 4. 数据流与控制流

### 4.1 工作空间初始化流程

```
[CLI 启动]
    │
    ▼
解析 --workspace 参数
    │
    ├──→ 提供值：使用该路径
    └──→ 未提供：使用 Config.workspace.default_path
    │
    ▼
调用 Workspace.initialize(root_path)
    │
    ├──→ root_path.resolve() 转为绝对路径
    │
    ├──→ 检查目录是否存在且可读
    │       └── 否 → 抛出 WorkspaceNotFoundError
    │
    ├──→ 存储为模块级单例
    │
    └──→ 调用 load_agents_md()
            ├──→ 存在：返回 AgentsMdContent → 注入 LLM 系统提示词
            └──→ 不存在：返回 None → 静默继续
```

### 4.2 路径解析流程（v2.0.0）

```
用户输入路径 "data/roads.shp"
    │
    ▼
Workspace.resolve_path("data/roads.shp", must_exist=True)
    │
    ├──→ 相对路径 → 拼接：workspace.root / "data/roads.shp"
    │
    ├──→ resolve() → /home/project/data/roads.shp
    │
    ├──→ must_exist=True → 检查存在性
    │       └── 不存在 → PathNotFoundError（友好提示，非安全拦截）
    │
    └──→ 返回 Path
```

```
用户输入绝对路径 "D:\gis\raw\roads.shp"
    │
    ▼
Workspace.resolve_path("D:\gis\raw\roads.shp")
    │
    ├──→ 绝对路径 → 直接 resolve()
    │
    ├──→ resolve() → D:\gis\raw\roads.shp
    │
    └──→ 返回 Path（不限制范围）
```

### 4.3 输出文件生成流程

```
用户输入 "processed/roads" + 扩展名 ".geojson"
    │
    ▼
Workspace.generate_output_path("processed/roads", ".geojson")
    │
    ├──→ 解析路径：workspace.root / "processed/roads"
    │
    ├──→ 生成时间戳：20260526_143052
    │
    ├──→ 构造文件名：roads_20260526_143052.geojson
    │
    └──→ 返回：/home/project/processed/roads_20260526_143052.geojson
```

---

## 5. 依赖关系

### 5.1 向上依赖

| 模块 | 接口 | 用途 |
|------|------|------|
| `config` | `get_config()` | 读取默认工作空间路径 |

### 5.2 向下暴露

| 接口 | 使用方 |
|------|--------|
| `Workspace.resolve_path()` | `core/`（路径规范化）、`templates/`（safe_path 过滤器） |
| `Workspace.generate_output_path()` | `templates/`（脚本生成时确定输出路径） |
| `Workspace.load_agents_md()` | `llm/`（注入系统提示词） |
| `Workspace.get_cwd()` | `cli/`（脚本执行时设置默认 cwd） |
| `get_workspace()` | 需要路径规范化或 cwd 的模块 |

---

## 6. 异常与错误处理

| 异常类型 | 触发条件 | 处理策略 |
|---------|---------|---------|
| `WorkspaceNotFoundError` | 指定的 `--workspace` 目录不存在 | CLI 打印错误并退出（退出码 2） |
| `WorkspaceNotFoundError` | 路径存在但不是目录（是文件） | 同上 |
| `PathNotFoundError` | `must_exist=True` 时输入文件不存在 | CLI 提示文件不存在，建议检查路径 |
| `WorkspaceError` | Agents.md 存在但读取失败（权限） | 打印警告，继续运行（非致命） |

---

## 7. 测试策略

### 7.1 单元测试覆盖

| 测试场景 | 验证点 |
|---------|--------|
| 正常初始化 | 绝对路径正确存储，root 属性返回 Path |
| 相对路径初始化 | `initialize(Path("./data"))` 正确 resolve |
| 不存在目录 | 抛出 WorkspaceNotFoundError |
| 文件作为路径 | 抛出 WorkspaceNotFoundError |
| 合法相对路径 | `resolve_path("a/b.shp")` 返回 workspace/a/b.shp |
| 绝对路径输入 | `resolve_path("/tmp/x.shp")` 返回 /tmp/x.shp，不拦截 |
| `must_exist=True` 且文件存在 | 正常返回 |
| `must_exist=True` 且文件不存在 | 抛出 PathNotFoundError |
| 输出文件生成 | 返回的路径含时间戳，以 workspace 为基准 |
| 输出文件绝对路径 | `generate_output_path("/tmp/out", ".sh")` 使用 /tmp 为基准 |
| Agents.md 存在 | 返回 AgentsMdContent，content 为全文 |
| Agents.md 不存在 | 返回 None |
| 未初始化访问 | `get_workspace()` 抛出 RuntimeError |
| 会话不可变性 | 相关属性为只读 |

### 7.2 集成测试场景

- 与 `config` 模块集成：`initialize(Path(get_config().workspace.default_path))` 正常工作
- 与 CLI 集成：`--workspace` 参数传递正确

### 7.3 Mock 策略

- 使用 `tmp_path` fixture 创建临时目录作为工作空间
- 使用 `monkeypatch` 修改 `get_config()` 返回值（如需测试默认值逻辑）
- 测试后清除模块级单例

---

## 8. 需求追溯表

| 需求 ID | 设计决策 | 代码文件/函数 | 说明 |
|:-------:|:--------:|:-------------:|------|
| F7 | DC-0010 | `Workspace.__init__()` | 工作空间初始化与规范化 |
| F7 | DC-0014 | `initialize()` / `get_workspace()` | 全局工作空间管理 |
| W1 | DC-0010 | `Workspace.root` | 输出文件默认放置位置（可覆盖） |
| W2 | DC-0010 | `Workspace.get_cwd()` | 脚本执行默认 cwd |
| F11 | DC-0013 | `Workspace.load_agents_md()` | Agents.md 自动加载 |
| P3 | DC-0012 | `generate_output_path()` | 时间戳防覆盖 |
| CODE-2 | DC-0010, DC-0011 | `resolve_path()` | 路径统一规范化入口 |

---

## 附录 A：变更记录

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| **v2.0.0** | **2026-05-27** | **重大设计变更**：工作空间定位从"安全沙箱"调整为"记忆锚点 + 默认操作目录"。移除了 `PathEscapeError` 和路径前缀匹配安全边界（DC-0011）。路径解析不再限制在工作空间内，GIS 数据可来自任意合法路径。 |
| v1.0.0 | 2026-05-26 | 初版，定义工作空间管理、路径安全校验、Agents.md 加载机制 |
