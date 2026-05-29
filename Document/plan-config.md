# plan-config

| 项目 | 内容 |
|------|------|
| 版本 | v1.0.0 |
| 状态 | 设计基线 |
| 作者 | - |
| 日期 | 2026-05-26 |

---

## 1. 设计概述

### 1.1 模块职责

提供 GIS Agent 的全局配置管理能力：配置文件的加载、校验、分层访问，以及环境变量覆盖机制。本模块是**所有上层模块的基础设施依赖**，在进程启动时完成一次性初始化，运行期间只读。

### 1.2 所属架构层次

基础设施层（横切关注点，被 CLI / core / llm 各层依赖）。

### 1.3 对应需求项

| 需求 ID | 需求描述 |
|:-------:|---------|
| F7 | 工作空间默认路径需可配置 |
| — | LLM 连接参数（base_url、auth_key、model_name）需集中管理 |

---

## 2. 设计决策

### DC-0001: 配置文件采用 JSON 格式

**决策**: 运行时配置文件使用 JSON，位于 `SourceCode/config/config.json`。

**理由**:
- JSON 是 Python 标准库原生支持格式，零额外依赖（符合 P5）
- 配置文件结构简单，无需 YAML 的锚点引用等高级特性
- 团队内 GIS 分析师熟悉 JSON

**替代方案**:
- YAML：语法更宽松，但需要 `PyYAML` 依赖（违反 P5）
- TOML：Python 3.11+ 有标准库支持，但项目要求 3.10+
- INI：层级表达能力弱

### DC-0002: 配置项按功能域分层

**决策**: 配置顶层按功能域分组：`llm`、`workspace`。

**理由**:
- 避免扁平命名空间膨胀（如 `llm_base_url` vs `llm.base_url`）
- 各模块只读取自己关心的子集，降低耦合
- 便于后续扩展新功能域

**分层结构**:
```json
{
  "llm": { "base_url": "", "auth_key": "", "model_name": "" },
  "workspace": { "default_path": ".", "allow_parent_access": false },
  "api": { "host": "0.0.0.0", "port": 8000 }
}
```

### DC-0003: 敏感字段支持环境变量覆盖

**决策**: `llm.auth_key` 等敏感字段允许通过环境变量覆盖配置文件中的值。

**理由**:
- 避免将 API Key 提交到 Git（符合 SEC-1）
- 容器化部署时可通过 secrets 注入
- 向后兼容：配置文件可保留空字符串或占位符

**覆盖规则**:
- 环境变量名：`GISAGENT_LLM_AUTH_KEY`（前缀 `GISAGENT_` + 大写路径用 `_` 连接）
- 优先级：环境变量 > 配置文件 > 硬编码默认值

### DC-0004: 启动时一次性校验，运行期只读

**决策**: 配置在进程启动时完成加载和校验，成功后封装为不可变对象。运行期间不允许动态修改。

**理由**:
- 尽早失败：启动时发现配置错误，避免运行中途崩溃
- 简化并发：只读配置无需锁保护
- 符合预期：CLI 工具的配置通常在启动参数中确定

### DC-0005: 单例模式管理配置实例

**决策**: 模块内部维护一个全局 Config 单例，通过 `get_config()` 获取。

**理由**:
- 避免将 Config 对象在各层函数间层层传递
- 模块内部隐藏实例管理，对外只暴露纯函数接口
- 启动时由 CLI 层调用 `load_config()` 完成初始化

---

## 3. 接口定义

### 3.1 数据模型

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class LLMConfig:
    """LLM 连接配置。"""
    base_url: str
    auth_key: str
    model_name: str


@dataclass(frozen=True)
class WorkspaceConfig:
    """工作空间默认配置。"""
    default_path: str = "."
    allow_parent_access: bool = False


@dataclass(frozen=True)
class APIConfig:
    """FastAPI 服务器配置。"""
    host: str = "0.0.0.0"
    port: int = 8000


@dataclass(frozen=True)
class Config:
    """全局配置根对象。"""
    llm: LLMConfig
    workspace: WorkspaceConfig
    api: APIConfig = APIConfig()
```

### 3.2 公共 API

```python
from pathlib import Path
from typing import Optional


def load_config(path: Optional[Path] = None) -> Config:
    """加载并校验配置文件，初始化全局单例。

    Args:
        path: 配置文件路径。默认为 SourceCode/config/config.json
              （相对于包根目录）。

    Returns:
        校验通过的配置对象。

    Raises:
        FileNotFoundError: 配置文件不存在。
        json.JSONDecodeError: JSON 格式错误。
        ValueError: 必填字段缺失或类型不匹配。

    Design:
        DC-0001, DC-0003, DC-0004, DC-0005
    """


def get_config() -> Config:
    """获取已加载的全局配置实例。

    Returns:
        Config 单例对象。

    Raises:
        RuntimeError: 在 load_config() 之前调用。

    Design:
        DC-0005
    """
```

### 3.3 配置字段约束

| 字段路径 | 类型 | 必填 | 默认值 | 约束 |
|---------|------|:----:|--------|------|
| `llm.base_url` | str | 是 | — | 非空，合法 URL 格式 |
| `llm.auth_key` | str | 是 | — | 非空，或通过环境变量提供 |
| `llm.model_name` | str | 是 | — | 非空 |
| `workspace.default_path` | str | 否 | `"."` | 非空 |
| `workspace.allow_parent_access` | bool | 否 | `false` | — |
| `api.host` | str | 否 | `"0.0.0.0"` | 非空 |
| `api.port` | int | 否 | `8000` | 1–65535 |

---

## 4. 数据流与控制流

### 4.1 配置加载流程

```
[CLI 启动]
    │
    ▼
解析 --config 参数（可选）
    │
    ▼
调用 load_config(path)
    │
    ├──→ 读取 config.json 文件内容
    │
    ├──→ json.loads() 解析为 dict
    │
    ├──→ 应用环境变量覆盖（DC-0003）
    │       ├── 扫描 GISAGENT_* 环境变量
    │       └── 按命名规则映射到配置字段
    │
    ├──→ 字段存在性检查（必填字段）
    │
    ├──→ 类型转换与校验（int/str/bool）
    │
    ├──→ 业务规则校验（chunk_overlap < chunk_size 等）
    │
    └──→ 构造 Config 对象（frozen dataclass）
    │
    ▼
存储为模块级单例
    │
    ▼
返回 Config 给 CLI
```

### 4.2 环境变量映射规则

| 环境变量名 | 覆盖字段 | 示例值 |
|-----------|---------|--------|
| `GISAGENT_LLM_BASE_URL` | `llm.base_url` | `https://api.example.com` |
| `GISAGENT_LLM_AUTH_KEY` | `llm.auth_key` | `sk-xxxxxxxx` |
| `GISAGENT_LLM_MODEL_NAME` | `llm.model_name` | `claude-opus` |
| `GISAGENT_WORKSPACE_DEFAULT_PATH` | `workspace.default_path` | `/data/gis` |
| `GISAGENT_API_HOST` | `api.host` | `127.0.0.1` |
| `GISAGENT_API_PORT` | `api.port` | `9000` |

---

## 5. 依赖关系

### 5.1 向上依赖

本模块不依赖任何项目内部模块（最底层基础设施）。

### 5.2 向下暴露

| 接口 | 使用方 |
|------|--------|
| `load_config()` | `cli/main.py`、`api/main.py`（启动时调用） |
| `get_config()` | `core/`、`llm/`、`cli/`、`api/`（运行时使用） |
| `Config` 及子 dataclass | 所有上层模块（类型注解） |

---

## 6. 异常与错误处理

| 异常类型 | 触发条件 | 处理策略 |
|---------|---------|---------|
| `FileNotFoundError` | 配置文件路径不存在 | 向上抛出让 CLI 打印友好错误后退出（退出码 2） |
| `json.JSONDecodeError` | JSON 语法错误 | 同上，打印具体行列号 |
| `ValueError` | 必填字段缺失 | 打印缺失字段名列表 |
| `ValueError` | 类型不匹配 | 打印期望类型与实际值 |
| `RuntimeError` | `get_config()` 在 `load_config()` 前调用 | 内部逻辑错误，打印堆栈 |

> **注意**: 所有异常在抛出前必须通过标准 `logging` 记录 ERROR 级别日志（符合 CODE-5）。

---

## 7. 测试策略

### 7.1 单元测试覆盖

| 测试场景 | 验证点 |
|---------|--------|
| 完整有效配置加载 | 所有字段正确解析，返回 Config 对象 |
| 缺失必填字段 | 抛出 ValueError，消息包含缺失字段名 |
| 类型错误 | 字符串传入 int 字段时抛出 ValueError |
| 环境变量覆盖 | `GISAGENT_LLM_AUTH_KEY` 覆盖配置文件值 |
| 默认值填充 | 省略可选字段时使用默认值 |
| 未初始化访问 | `get_config()` 在 `load_config()` 前调用抛出 RuntimeError |

### 7.2 Mock 策略

- 使用 `tmp_path` fixture 创建临时配置文件
- 使用 `monkeypatch.setenv()` 模拟环境变量
- 在每个测试用例后清除模块级单例（防止测试间污染）

---

## 8. 需求追溯表

| 需求 ID | 设计决策 | 代码文件/函数 | 说明 |
|:-------:|:--------:|:-------------:|------|
| F7 | DC-0002 | `Config.workspace.default_path` | 工作空间默认路径 |
| — | DC-0003 | `load_config()` 环境变量逻辑 | 敏感信息隔离 |
| P5 | DC-0001 | `json` 标准库 | 零额外依赖 |
| SEC-1 | DC-0003 | 环境变量覆盖机制 | auth_key 不硬编码提交 |

---

## 附录：变更记录

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.0.0 | 2026-05-26 | 初版，定义配置分层结构、校验规则、环境变量覆盖 |
| v1.1.0 | 2026-05-29 | 新增 `api` 配置域（`host`、`port`），支持 FastAPI 服务器地址可配置 |
