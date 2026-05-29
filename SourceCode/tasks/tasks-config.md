# tasks-config — config 模块实现任务清单

| 项目 | 内容 |
|------|------|
| 来源 Plan | [plan-config](../Document/plan-config.md) v1.1.0 |
| 状态 | **已完成** |
| 创建日期 | 2026-05-27 |
| 更新日期 | 2026-05-29 |

---

## 任务总览

| 任务 ID | 任务名称 | 关联设计决策 | 优先级 | 状态 |
|:-------:|---------|:----------:|:------:|:----:|
| C-01 | 创建模块目录与 `__init__.py` | — | P0 | **已完成** |
| C-02 | 实现配置数据模型（frozen dataclasses） | DC-0002 | P0 | **已完成** |
| C-03 | 实现配置加载与解析（`load_config`） | DC-0001, DC-0003, DC-0004 | P0 | **已完成** |
| C-04 | 实现环境变量覆盖机制 | DC-0003 | P0 | **已完成** |
| C-05 | 实现配置校验逻辑 | DC-0004 | P0 | **已完成** |
| C-06 | 实现全局单例访问（`get_config`） | DC-0005 | P0 | **已完成** |
| C-07 | 实现默认配置文件（`config.json`） | DC-0001 | P0 | **已完成** |
| C-08 | 编写单元测试 | — | P0 | **已完成** |
| C-09 | 运行质量门禁检查 | — | P0 | **已完成** |

---

## C-02: 实现配置数据模型（frozen dataclasses）

**关联设计决策**: DC-0002（配置项按功能域分层）

**目标文件**: `SourceCode/src/config/models.py`

**已实现 dataclass**:

1. `LLMConfig` — 字段：`base_url` (str), `auth_key` (str), `model_name` (str)
2. `WorkspaceConfig` — 字段：`default_path` (str, default="."), `allow_parent_access` (bool, default=False)
3. `Config` — 字段：`llm` (LLMConfig), `workspace` (WorkspaceConfig)

> **注意**: 原设计中包含 `EmbeddingConfig` 和 `RAGConfig`，已于 2026-05-29 移除（ADR-0001）。

---

## C-04: 实现环境变量覆盖机制

**关联设计决策**: DC-0003（敏感字段支持环境变量覆盖）

**已实现环境变量映射**:

- `GISAGENT_LLM_BASE_URL` → `llm.base_url`
- `GISAGENT_LLM_AUTH_KEY` → `llm.auth_key`
- `GISAGENT_LLM_MODEL_NAME` → `llm.model_name`
- `GISAGENT_WORKSPACE_DEFAULT_PATH` → `workspace.default_path`
- `GISAGENT_WORKSPACE_ALLOW_PARENT_ACCESS` → `workspace.allow_parent_access`

> **注意**: `GISAGENT_EMBEDDING_MODEL_PATH`、`GISAGENT_EMBEDDING_DEVICE`、`GISAGENT_RAG_CHUNK_SIZE`、`GISAGENT_RAG_TOP_K` 已随 RAG 子系统移除而删除。

---

## C-05: 实现配置校验逻辑

**已实现校验项**:

- `llm.base_url`, `llm.auth_key`, `llm.model_name` — 必填
- `llm.base_url` — 非空且以 `http://` 或 `https://` 开头
- `workspace.default_path` — 非空
- `workspace.allow_parent_access` — 必须为 bool

> **注意**: 原设计中的 `chunk_overlap < chunk_size`、`embedding.model_path` 存在性检查、`device` 枚举校验已随 RAG/embedding 移除而删除。

---

## C-07: 实现默认配置文件

**当前 `config.json.template` 结构**:

```json
{
  "llm": {
    "base_url": "https://api.kimi.com/coding/",
    "auth_key": "",
    "model_name": "K2.6"
  },
  "workspace": {
    "default_path": ".",
    "allow_parent_access": false
  }
}
```

---

## C-08: 编写单元测试

**目标文件**: `SourceCode/tests/unit/test_config.py`

**已实现测试用例**:

| 测试函数名 | 测试场景 | 验证点 |
|-----------|---------|--------|
| `test_load_valid_config` | 完整有效配置加载 | 所有字段正确解析，返回 Config 对象 |
| `test_missing_required_fields` | 缺失必填字段 | 抛出 ValueError，消息包含缺失字段名 |
| `test_type_error` | 类型错误 | 字符串传入 int 字段时抛出 ValueError |
| `test_env_override` | 环境变量覆盖 | `GISAGENT_LLM_AUTH_KEY` 覆盖配置文件值 |
| `test_defaults_filled` | 默认值填充 | 省略可选字段时使用默认值 |
| `test_uninitialized_get_config` | 未初始化访问 | `get_config()` 在 `load_config()` 前调用抛出 RuntimeError |
| `test_url_validation` | URL 格式校验 | 空/非法 URL 抛出 ValueError |

---

## 需求追溯链

```
spec.md
├── F7 (工作空间默认路径可配置) ──→ DC-0002 ──→ C-02 (WorkspaceConfig)
├── P5 (最小依赖) ──→ DC-0001 ──→ C-03 (json标准库)
├── SEC-1 (不硬编码API Key) ──→ DC-0003 ──→ C-04 (环境变量覆盖)
└── CODE-5 (except必须log或re-raise) ──→ C-03 (异常处理)
```

> **注意**: F1（RAG 参数可配置）已随 RAG 子系统移除而废弃。

---

## 附录：文件清单

| 文件路径 | 用途 | 关联任务 |
|---------|------|---------|
| `src/config/__init__.py` | 包初始化与公共导出 | C-01 |
| `src/config/models.py` | 配置数据模型 | C-02 |
| `src/config/loader.py` | 加载、校验、单例管理 | C-03, C-04, C-05, C-06 |
| `config/config.json` | 默认配置文件 | C-07 |
| `tests/unit/test_config.py` | 单元测试 | C-08 |
