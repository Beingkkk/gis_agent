# ADR-0004: 引入 `pydantic` 替代手写配置加载与验证逻辑

## 状态

- 已提出

## 上下文

`config/loader.py` 负责 GIS Agent 的全局配置管理，当前实现完全基于标准库：

1. **JSON 读取** — 手动 `json.loads()` + 路径解析
2. **环境变量覆盖** — `_apply_env_overrides()` 手动维护 `env_map` 字典，逐字段映射 `GISAGENT_LLM_BASE_URL` → `raw["llm"]["base_url"]`
3. **校验** — `_validate_config()` 手写必填字段检查、URL 格式检查、类型检查
4. **组装** — `_build_config()` 手动从 dict 提取字段构造 `LLMConfig` / `Config` dataclass
5. **单例管理** — 模块级 `_config_instance` + `load_config()` / `get_config()`

合计 ~200 行，核心问题：

- **重复造轮子**：配置验证、环境变量映射、嵌套模型构造是几乎每个 Python 项目都需要的通用能力，pydantic 生态已提供成熟解决方案
- **扩展成本高**：每新增一个配置项需要修改 4 处（env_map、validation、defaults、builder）
- **错误消息不一致**：手写校验的错误消息风格各异，不如 pydantic 的标准化 ValidationError
- **类型安全弱**：dataclass 在运行时无验证，`Config(base_url=123)` 不会报错直到使用时才发现

`config/models.py` 中的 `Config` / `LLMConfig` 使用 `frozen dataclass`，仅提供数据容器功能，无运行时验证。

## 决策

1. **引入 `pydantic` 作为生产依赖**。使用 `pydantic.BaseModel` 替代手写 dataclass + 验证逻辑：
   - `LLMConfig` → `BaseModel(frozen=True)`，字段约束：`base_url` 用 `pattern=r"^https?://"` 自动校验 URL 格式；`auth_key` / `model_name` 用 `min_length=1` 自动校验非空
   - `Config` → `BaseModel(frozen=True)`，嵌套 `LLMConfig`
   - 环境变量覆盖通过 `model_validator(mode="before")` 在模型验证前自动应用

2. **`pydantic-settings` 作为配套依赖同时引入**。虽然当前方案基于 `BaseModel` 而非 `BaseSettings`（原因见§3），但 `pydantic-settings` 是 `pydantic` v2 生态的标准配套库。引入后为未来扩展预留能力（如 `.env` 文件支持、secrets 目录、更丰富的多源配置合并）。

3. **不使用 `BaseSettings` 的原因**：`pydantic.BaseSettings` 的默认优先级中，初始化 kwargs 高于环境变量。这意味着 `Config(**json_dict)` 传入的 JSON 值不会被环境变量覆盖——这与当前需求（JSON 文件为默认值，环境变量可覆盖）矛盾。通过 `settings_customise_sources` 调整优先级需要运行时动态指定 JSON 文件路径，与 `BaseSettings` 的类级配置模型不匹配。`BaseModel` + `model_validator` 更直接地实现相同效果。

4. **接口契约不变**：
   - `load_config(path: Optional[Path]) -> Config` 签名不变
   - `get_config() -> Config` 签名不变
   - `Config` / `LLMConfig` 的公共属性访问不变（`cfg.llm.base_url`）
   - `_clear_config_singleton()` 保留（测试用）

5. **错误消息迁移**：pydantic 的 `ValidationError` 在 `load_config()` 中被捕获并包装为 `ValueError`，保持调用方的异常契约。

## 后果

### 正面影响

| 方面 | 说明 |
|------|------|
| **代码简化** | `config/loader.py` 从 ~200 行缩减至 ~50 行。删除 `_bool_from_env`、`_apply_env_overrides`、`_validate_config`、`_fill_defaults`、`_build_config` 五个函数 |
| **验证增强** | URL 格式、非空检查、嵌套结构完整性由 pydantic 自动处理，无需手写正则和条件分支 |
| **类型安全** | 运行时验证：`Config.model_validate({"llm": {"base_url": 123}})` 立即抛出 ValidationError |
| **维护减负** | 新增配置项只需在 `LLMConfig` 中添加一个 `Field(...)` 声明，环境变量映射、验证、错误消息自动生成 |
| **错误消息标准化** | pydantic 的 ValidationError 提供字段级定位（`llm.base_url`）、约束类型（`string_pattern_mismatch`）、输入值预览，比手写的 `"Missing required fields"` 更精确 |

### 负面影响 / 风险

| 风险 | 说明 | 缓解措施 |
|------|------|---------|
| 供应链面扩大 | 新增两个第三方依赖（`pydantic` + `pydantic-settings`） | `pydantic` v2 是 Python 生态事实标准（FastAPI、SQLModel 等广泛依赖），维护活跃；`pydantic-settings` 是官方配套库 |
| P5 约束放宽 | 生产依赖从 4 个增至 6 个 | 本 ADR 本身即为批准记录；`pydantic` 被明确纳入已批准依赖白名单 |
| 错误消息格式变化 | `ValueError("Missing required fields: ...")` 变为 `ValueError("Config validation failed: ...")` + pydantic 详细错误 | 测试同步更新；外层仍是 `ValueError`，调用方捕获逻辑不变 |
| frozen 行为差异 | dataclass 的 `FrozenInstanceError` 变为 pydantic 的 `ValidationError(type=frozen_instance)` | 测试同步更新；运行时效果相同（修改抛出异常） |
| 性能 | pydantic v2 基于 Rust 核心（pydantic-core），解析速度极快；配置加载仅在进程启动时执行一次，无热路径影响 | — |

## 替代方案

### 替代方案 A：继续维护手写配置逻辑

保留现有的 `_apply_env_overrides`、`_validate_config`、`_build_config`，针对新配置项继续扩展。

**否决理由**：边际收益递减。当前配置结构虽简单，但手写验证逻辑已达 ~80 行，超过引入一个成熟库的代价。且每新增字段都需要改 4 处，维护成本线性增长。

### 替代方案 B：使用 `pydantic.BaseSettings`（而非 `BaseModel`）

使用 `BaseSettings` 的自动环境变量映射和 JSON 文件源支持。

**否决理由**：`BaseSettings` 默认优先级中 kwargs > env，导致 `Config(**json_dict)` 传入的 JSON 值无法被环境变量覆盖。调整优先级需通过 `settings_customise_sources`，但 JSON 文件路径需要运行时传入（`load_config(path)`），与 `BaseSettings` 的类级配置模型不匹配。`BaseModel` + `model_validator` 更直接。

### 替代方案 C：使用 `python-dotenv` + `os.environ`

引入 `python-dotenv` 读取 `.env` 文件，手动映射到 dataclass。

**否决理由**：项目不使用 `.env` 文件（配置通过 JSON + 环境变量），`python-dotenv` 提供的能力与当前需求无关。不如一步到位引入 pydantic，同时解决验证、嵌套模型、环境变量覆盖三个问题。

## 相关文档

- `Document/spec.md` — §4.1 依赖栈、§6 P5 原则（需更新以反映 pydantic 纳入白名单）
- `Document/constitution.md` — §6.2 依赖规则、§8.2 质量门禁
- `Document/plan-core.md` — §9 配置子模块（DC-0001~DC-0005，需更新）
- `Document/archive/plan-config.md` — DC-0001~DC-0005 原始设计（需标注已迁移）
- `SourceCode/src/config/models.py` — 数据模型重构
- `SourceCode/src/config/loader.py` — 配置加载逻辑重构
- `SourceCode/pyproject.toml` — 生产依赖声明
