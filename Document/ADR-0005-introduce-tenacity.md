# ADR-0005: 引入 `tenacity` 替换手写 LLM 重试循环

## 状态

已批准（Approved）

## 上下文

`llm/client.py` 的 `LLMClient.chat()` 方法需要处理 LLM 调用过程中的 transient 失败：网络连接中断、请求超时、服务端限流、服务端 5xx 错误。当前实现采用手写 `for attempt in range(...)` 循环，在 4 个独立的 `except` 分支中重复完全相同的指数退避逻辑（日志 → `time.sleep(delay)` → `delay *= 2`）。

这段逻辑占据 `chat()` 方法约 100 行，真正的业务调用和精细错误分类（4xx 认证 / 400 上下文长度）被淹没在循环噪音中，且任何退避策略调整都需要同时修改 4 处。

## 决策

批准引入 `tenacity` 作为生产依赖，使用其声明式 `@retry` 装饰器表达 LLM 重试策略：

- `stop_after_attempt(4)`：最大尝试 4 次（含首次），与原 `MAX_RETRIES=3` 语义一致。
- `wait_exponential(multiplier=1, min=1, max=8)`：指数退避 1s → 2s → 4s → 8s，与原逻辑一致。
- `retry_if_exception(_should_retry)`：通过集中函数判断异常是否属于 transient（连接、超时、RateLimit、APIStatusError 429 / 5xx）。
- `before_sleep=_log_retry_attempt`：在每次重试前统一打印与原日志格式兼容的 warning。
- `reraise=True`：保留原始异常传播；外层通过 `except RetryError` 在全部尝试耗尽后，按原逻辑包装为 `LLMConnectionError` 或 `LLMRateLimitError`。

不可重试的异常（401/403/400/其他 4xx、`AuthenticationError`、`PermissionDeniedError`）仍保留在 `chat()` 内部处理，直接抛出对应的业务异常，不进入 tenacity 重试路径。

## 后果

### 正面

- **删除约 85 行重复代码**：4 个完全相同的 `except ...: last_error = exc; ...; time.sleep(delay); delay *= 2` 块被替换为 15 行左右的装饰器配置。
- **重试策略集中可见**：策略参数（尝试次数、退避方式、可重试异常白名单）从分散的 `except` 分支提升为一目了然的装饰器参数。
- **策略增强零成本**：未来如需增加抖动（jitter）、总时间预算、自定义回调，只需修改装饰器参数，无需重写循环。
- **`chat_stream()` 可复用**：当前 stream 明确不 retry；未来若需在流起始阶段重试，可直接复用同一套 `@retry` 策略。

### 负面

- **生产依赖 +1**：`pyproject.toml` 生产依赖从 6 个增加到 7 个，P5 约束上限从 ≤6 调整为 ≤7。
- **团队学习成本**：维护者需要了解 `tenacity` 的基本概念（`RetryCallState`、`RetryError`、`before_sleep`）。
- **调试路径变化**：重试日志不再由业务代码直接打印，而是通过 `before_sleep` 回调统一输出，需要定位到装饰器配置才能修改格式。

## 影响范围

| 文件 | 变更内容 |
|------|----------|
| `SourceCode/pyproject.toml` | 生产依赖增加 `tenacity` |
| `SourceCode/src/llm/client.py` | 手写 retry 循环 → `@retry` 装饰器 + `_should_retry` / `_log_retry_attempt` |
| `SourceCode/tests/unit/test_llm_client.py` | 调整 retry 测试：不再断言 `time.sleep` 调用细节，改为断言尝试次数和最终异常包装 |
| `Document/spec.md` | §4.1 / §6 P5 / §7.2 更新依赖数量；附录 B 增加 v1.10.0 修订记录 |
| `Document/constitution.md` | P5 描述增加 ADR-0005 引用 |
