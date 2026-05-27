# tasks-config — config 模块实现任务清单

| 项目 | 内容 |
|------|------|
| 来源 Plan | [plan-config](../Document/plan-config.md) v1.0.0 |
| 状态 | 待实现 |
| 创建日期 | 2026-05-27 |

---

## 任务总览

| 任务 ID | 任务名称 | 关联设计决策 | 优先级 | 状态 |
|:-------:|---------|:----------:|:------:|:----:|
| C-01 | 创建模块目录与 `__init__.py` | — | P0 | 待办 |
| C-02 | 实现配置数据模型（frozen dataclasses） | DC-0002 | P0 | 待办 |
| C-03 | 实现配置加载与解析（`load_config`） | DC-0001, DC-0003, DC-0004 | P0 | 待办 |
| C-04 | 实现环境变量覆盖机制 | DC-0003 | P0 | 待办 |
| C-05 | 实现配置校验逻辑 | DC-0004 | P0 | 待办 |
| C-06 | 实现全局单例访问（`get_config`） | DC-0005 | P0 | 待办 |
| C-07 | 实现默认配置文件（`config.json`） | DC-0001 | P0 | 待办 |
| C-08 | 编写单元测试 | — | P0 | 待办 |
| C-09 | 运行质量门禁检查 | — | P0 | 待办 |

---

## C-01: 创建模块目录与 `__init__.py`

**关联设计决策**: 模块初始化

**目标文件**:
- `SourceCode/src/config/__init__.py`
- `SourceCode/src/config/loader.py`
- `SourceCode/src/config/models.py`

**任务内容**:
1. 在 `SourceCode/src/` 下创建 `config/` 包目录
2. 创建 `__init__.py`，导出公共 API：`load_config`, `get_config`, `Config` 及各子配置类
3. 创建 `models.py` 存放数据模型
4. 创建 `loader.py` 存放加载与校验逻辑

**验收标准**:
- `from src.config import load_config, get_config, Config` 可正常导入
- 目录结构符合架构分层约定（基础设施层）

---

## C-02: 实现配置数据模型（frozen dataclasses）

**关联设计决策**: DC-0002（配置项按功能域分层）

**目标文件**: `SourceCode/src/config/models.py`

**任务内容**:
实现以下 5 个 frozen dataclass：

1. `LLMConfig` — 字段：`base_url` (str), `auth_key` (str), `model_name` (str)
2. `EmbeddingConfig` — 字段：`model_path` (str), `device` (Literal["cpu", "cuda"], default="cpu")
3. `RAGConfig` — 字段：`chunk_size` (int, default=512), `chunk_overlap` (int, default=128), `top_k` (int, default=5)
4. `WorkspaceConfig` — 字段：`default_path` (str, default="."), `allow_parent_access` (bool, default=False)
5. `Config` — 字段：`llm` (LLMConfig), `embedding` (EmbeddingConfig), `rag` (RAGConfig), `workspace` (WorkspaceConfig)

**验收标准**:
- 所有 dataclass 均标记 `@dataclass(frozen=True)`
- 类型注解完整，可通过 `mypy --strict` 检查
- 可正确实例化：`Config(llm=LLMConfig(...), embedding=..., rag=..., workspace=...)`

---

## C-03: 实现配置加载与解析（`load_config`）

**关联设计决策**: DC-0001（JSON 格式配置）, DC-0004（启动时一次性校验）

**目标文件**: `SourceCode/src/config/loader.py`

**任务内容**:
实现 `load_config(path: Optional[Path] = None) -> Config` 函数：

1. 默认路径为包内 `SourceCode/config/config.json`
2. 读取文件内容 → `json.loads()` 解析为 dict
3. 应用环境变量覆盖（见 C-04）
4. 校验必填字段与类型（见 C-05）
5. 构造并返回 `Config` 对象
6. 存储为模块级单例变量 `_config_instance`

**异常处理**（按 constitution §CODE-5）：
- `FileNotFoundError` → 抛出前记录 ERROR 日志
- `json.JSONDecodeError` → 抛出前记录 ERROR 日志
- `ValueError`（字段缺失/类型错误/业务规则违反）→ 抛出前记录 ERROR 日志

**验收标准**:
- 传入有效配置文件路径可成功加载并返回 `Config`
- 缺失必填字段时抛出 `ValueError`，消息包含缺失字段名
- JSON 语法错误时抛出 `json.JSONDecodeError`
- 所有异常抛出前均有 `logging.error` 记录

---

## C-04: 实现环境变量覆盖机制

**关联设计决策**: DC-0003（敏感字段支持环境变量覆盖）

**目标文件**: `SourceCode/src/config/loader.py`

**任务内容**:
实现环境变量扫描与映射逻辑：

1. 扫描所有以 `GISAGENT_` 开头的环境变量
2. 按命名规则映射到配置字段：
   - `GISAGENT_LLM_BASE_URL` → `llm.base_url`
   - `GISAGENT_LLM_AUTH_KEY` → `llm.auth_key`
   - `GISAGENT_LLM_MODEL_NAME` → `llm.model_name`
   - `GISAGENT_EMBEDDING_MODEL_PATH` → `embedding.model_path`
   - `GISAGENT_EMBEDDING_DEVICE` → `embedding.device`
   - `GISAGENT_RAG_CHUNK_SIZE` → `rag.chunk_size`
   - `GISAGENT_RAG_TOP_K` → `rag.top_k`
   - `GISAGENT_WORKSPACE_DEFAULT_PATH` → `workspace.default_path`
3. 优先级：环境变量 > 配置文件 > 硬编码默认值
4. 覆盖时进行类型转换（环境变量值为字符串，需转为 int/bool）

**验收标准**:
- 设置 `GISAGENT_LLM_AUTH_KEY=sk-test` 后，加载配置时 `config.llm.auth_key == "sk-test"`
- 环境变量 `GISAGENT_RAG_CHUNK_SIZE=1024` 可正确转为 int
- 环境变量 `GISAGENT_WORKSPACE_ALLOW_PARENT_ACCESS=true` 可正确转为 bool
- 未设置的环境变量不干扰配置文件原有值

---

## C-05: 实现配置校验逻辑

**关联设计决策**: DC-0004（启动时一次性校验）

**目标文件**: `SourceCode/src/config/loader.py`

**任务内容**:
实现分层校验函数 `_validate_config(raw: dict) -> None`：

**字段存在性检查**（必填字段）：
- `llm.base_url`, `llm.auth_key`, `llm.model_name`
- `embedding.model_path`

**类型转换与校验**：
- `chunk_size` / `chunk_overlap` / `top_k` 必须可转为正整数
- `device` 必须是 `"cpu"` 或 `"cuda"`
- `allow_parent_access` 必须可转为 bool

**业务规则校验**：
- `chunk_overlap < chunk_size`
- `llm.base_url` 非空且为合法 URL 格式（以 `http://` 或 `https://` 开头）
- `embedding.model_path` 指向存在的路径（文件或目录）

**默认值填充**：
- 可选字段省略时填入硬编码默认值

**验收标准**:
- `chunk_overlap >= chunk_size` 时抛出 `ValueError`，消息说明规则
- `llm.base_url = ""` 时抛出 `ValueError`
- `device = "gpu"` 时抛出 `ValueError`
- 缺失必填字段时一次性列出所有缺失字段名

---

## C-06: 实现全局单例访问（`get_config`）

**关联设计决策**: DC-0005（单例模式）

**目标文件**: `SourceCode/src/config/loader.py`

**任务内容**:
实现 `get_config() -> Config` 函数：

1. 返回模块级单例 `_config_instance`
2. 若在 `load_config()` 之前调用，抛出 `RuntimeError`，提示必须先调用 `load_config()`

**验收标准**:
- 先调用 `load_config()` 再调用 `get_config()` 可正确返回 `Config`
- 未调用 `load_config()` 时 `get_config()` 抛出 `RuntimeError`
- 多次调用 `get_config()` 返回同一对象

---

## C-07: 实现默认配置文件（`config.json`）

**关联设计决策**: DC-0001（JSON 格式配置）

**目标文件**: `SourceCode/config/config.json`

**任务内容**:
创建默认配置文件，结构与 plan-config §3.2 一致：

```json
{
  "llm": {
    "base_url": "",
    "auth_key": "",
    "model_name": "claude-sonnet-4-6"
  },
  "embedding": {
    "model_path": "SourceCode/model/paraphrase-multilingual-MiniLM-L12-v2",
    "device": "cpu"
  },
  "rag": {
    "chunk_size": 512,
    "chunk_overlap": 128,
    "top_k": 5
  },
  "workspace": {
    "default_path": ".",
    "allow_parent_access": false
  }
}
```

**注意**: `auth_key` 留空，要求用户通过环境变量 `GISAGENT_LLM_AUTH_KEY` 提供（符合 SEC-1）。

**验收标准**:
- JSON 语法有效
- 所有必填字段存在（即使值为空字符串）
- `load_config()` 默认路径可成功读取此文件（配合环境变量后通过校验）

---

## C-08: 编写单元测试

**关联设计决策**: plan-config §7（测试策略）

**目标文件**: `SourceCode/tests/unit/test_config.py`

**任务内容**:
覆盖以下测试场景：

| 测试函数名 | 测试场景 | 验证点 |
|-----------|---------|--------|
| `test_load_valid_config` | 完整有效配置加载 | 所有字段正确解析，返回 Config 对象 |
| `test_missing_required_fields` | 缺失必填字段 | 抛出 ValueError，消息包含缺失字段名 |
| `test_type_error` | 类型错误 | 字符串传入 int 字段时抛出 ValueError |
| `test_business_rule_overlap` | 业务规则违反 | `chunk_overlap >= chunk_size` 时抛出 ValueError |
| `test_env_override` | 环境变量覆盖 | `GISAGENT_LLM_AUTH_KEY` 覆盖配置文件值 |
| `test_defaults_filled` | 默认值填充 | 省略可选字段时使用默认值 |
| `test_uninitialized_get_config` | 未初始化访问 | `get_config()` 在 `load_config()` 前调用抛出 RuntimeError |
| `test_url_validation` | URL 格式校验 | 空/非法 URL 抛出 ValueError |
| `test_model_path_existence` | 模型路径存在性 | 不存在的路径抛出 ValueError |

**Mock 策略**:
- 使用 `tmp_path` fixture 创建临时配置文件
- 使用 `monkeypatch.setenv()` 模拟环境变量
- 在每个测试用例后清除模块级单例（防止测试间污染）

**验收标准**:
- 所有测试用例通过 `pytest`
- 覆盖率 >= 80%（质量门禁要求）

---

## C-09: 运行质量门禁检查

**关联设计决策**: constitution §8（质量门禁）

**任务内容**:
对实现的代码运行以下检查：

```bash
# 格式化
ruff format src/config/ tests/unit/test_config.py

# 风格与错误检查
ruff check src/config/ tests/unit/test_config.py

# 严格类型检查
mypy --strict src/config/

# 单元测试（覆盖率）
pytest tests/unit/test_config.py -v --cov=src.config --cov-report=term-missing
```

**验收标准**:
- `ruff check` 无错误
- `mypy --strict` 无类型错误
- `pytest` 全部通过，覆盖率 >= 80%

---

## 需求追溯链

```
spec.md
├── F1 (RAG参数可配置) ──→ DC-0002 ──→ C-02 (RAGConfig)
├── F7 (工作空间默认路径可配置) ──→ DC-0002 ──→ C-02 (WorkspaceConfig)
├── P5 (最小依赖) ──→ DC-0001 ──→ C-03 (json标准库)
├── SEC-1 (不硬编码API Key) ──→ DC-0003 ──→ C-04 (环境变量覆盖)
└── CODE-5 (except必须log或re-raise) ──→ C-03 (异常处理)
```

---

## 附录：文件清单

| 文件路径 | 用途 | 关联任务 |
|---------|------|---------|
| `src/config/__init__.py` | 包初始化与公共导出 | C-01 |
| `src/config/models.py` | 配置数据模型 | C-02 |
| `src/config/loader.py` | 加载、校验、单例管理 | C-03, C-04, C-05, C-06 |
| `config/config.json` | 默认配置文件 | C-07 |
| `tests/unit/test_config.py` | 单元测试 | C-08 |
