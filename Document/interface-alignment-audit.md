# 前后端接口对齐审计报告

> **状态**：✅ 约束已写入 constitution.md（CODE-5）+ spec.md（§4.3.1）

## 背景

用户反馈 Q&A Tab "有时可以，有时超时"。排查发现根本原因是：

- **plan 设计**：Q&A 应使用 WebSocket 流式 (`/ws/chat/{session_id}`)
- **实际实现**：前端使用 HTTP POST (`POST /session/{id}/chat`)，30秒超时
- **LLM 调用**：有时超过 30s → axios 超时断开 → 显示"处理失败"

这引发了对全部前后端接口对齐情况的全盘审计。

---

## 审计方法

1. 读取全部 `Document/plan-*.md` 中的接口设计
2. 读取全部 `SourceCode/src/api/routes/*.py` 和 `websocket/*.py` 实际实现
3. 读取全部 `SourceCode/frontend/src/api/*.ts` 前端调用
4. 逐一比对

---

## 一、对齐状态总表

### REST API

| 端点 | 方法 | 用途 | 后端实现 | 前端调用 | 对齐状态 |
|------|------|------|---------|---------|---------|
| `/session` | POST | 创建会话 | ✅ session.py | ✅ session.ts | ✅ |
| `/session/{id}/intent` | POST | DiscoveryTab 意图匹配 | ✅ session.py | ✅ session.ts | ✅ |
| `/session/{id}/chat` | POST | Q&A (HTTP fallback) | ✅ session.py | ⚠️ 已弃用 | ⚠️ 见注1 |
| `/session/{id}/lock` | POST | 锁定模板 | ✅ session.py | ✅ session.ts | ✅ |
| `/session/{id}/params` | POST | 提交参数 | ✅ session.py | ✅ session.ts | ✅ |
| `/session/{id}/execute` | POST | 触发执行 | ✅ session.py | ✅ session.ts | ✅ |
| `/session/{id}` | GET | 获取会话状态 | ✅ session.py | ✅ session.ts | ✅ |
| `/session/{id}/clear` | POST | 清空会话 | ✅ session.py | ✅ session.ts | ✅ |
| `/session/{id}/workspace` | POST | 切换工作空间 | ✅ session.py | ✅ session.ts | ✅ |
| `/session/{id}/diagnose` | POST | 错误诊断 | ✅ session.py | ✅ session.ts | ✅ |
| `/session/{id}/exec-env` | POST | 保存执行环境 | ✅ exec_env.py | ✅ execEnv.ts | ✅ |
| `/templates` | GET | 模板列表 | ✅ templates.py | ✅ templates.ts | ✅ |
| `/templates/{id}` | GET | 模板详情 | ✅ templates.py | ✅ templates.ts | ✅ |
| `/pipeline` | POST | Pipeline 预览 | ✅ pipeline.py | ✅ pipeline.ts | ✅ |
| `/pipeline/execute` | POST | 触发 Pipeline 执行 | ✅ pipeline.py | ✅ pipeline.ts | ✅ |
| `/generator/generate` | POST | 生成 J2 模板 | ✅ generator.py | ✅ generator.ts | ✅ |
| `/generator/validate` | POST | 校验模板 | ✅ generator.py | ✅ generator.ts | ✅ |
| `/generator/save` | POST | 保存模板 | ✅ generator.py | ✅ generator.ts | ✅ |
| `/exec-env/verify` | POST | 验证执行环境 | ✅ exec_env.py | ✅ execEnv.ts | ✅ |
| `/exec-env/conda-envs` | GET | conda 环境列表 | ✅ exec_env.py | ✅ execEnv.ts | ✅ |
| `/health` | GET | 健康检查 | ✅ main.py | ✅ health.ts | ✅ |

### WebSocket

| 端点 | 用途 | 后端实现 | 前端调用 | 对齐状态 |
|------|------|---------|---------|---------|
| `/ws/chat/{session_id}` | Q&A 流式对话 | ✅ chat.py | ✅ 已修复 | ✅ |
| `/ws/execute/{session_id}` | 脚本执行实时日志 | ✅ execute.py | ✅ MainPage.tsx | ✅ |
| `/ws/pipeline-execute/{execution_id}` | Pipeline 执行实时日志 | ❌ **未实现** | ❌ 未使用 | ❌ 见注2 |

---

## 二、发现的不对齐问题

### 问题 1：Q&A 前端使用 HTTP 而非 WebSocket（已修复 ✅）

**影响**：用户看到的"有时超时"错误

| 维度 | 设计 | 实现 |
|------|------|------|
| plan-ux.md | `/ws/chat/{session_id}` WebSocket 流式 | ✅ 后端已实现 |
| 前端实际 | `POST /session/{id}/chat` HTTP，30s 超时 | ❌ 已修复 |

**根因**：后端 `websocket/chat.py` 早已实现流式 Q&A，但前端 `MainPage.tsx` 的 `handleQASend` 一直使用 `chatQuestion()` HTTP 调用。

**修复**：已将 `handleQASend` 改为 WebSocket 连接 `/ws/chat/{session_id}`，实时接收 chunk 并更新消息。`QATab` 新增 `isStreaming` prop，流式输出时不显示 loading 弹跳点。

**修改文件**：
- `frontend/src/hooks/useSession.ts` — 新增 `updateLastQAMessage()`
- `frontend/src/pages/MainPage.tsx` — `handleQASend` 改用 WebSocket
- `frontend/src/components/QATab.tsx` — 新增 `isStreaming` prop

---

### 问题 2：Pipeline 执行 WebSocket 未实现（未修复 ❌）

**影响**：Pipeline 执行如果脚本运行时间长，同样会遇到超时问题

| 维度 | 设计 | 实现 |
|------|------|------|
| plan-pipeline-execute.md | `/ws/pipeline-execute/{execution_id}` WebSocket | ❌ 后端未实现 |
| 后端实际 | 只有 `POST /pipeline/execute` HTTP | ❌ 无 WebSocket handler |
| 前端实际 | 只调用了 HTTP `executePipeline()` | ❌ 无 WebSocket 连接 |

**plan-pipeline-execute.md 设计要求**：
- 新增 WebSocket 端点 `/ws/pipeline-execute/{execution_id}`
- 帧类型：`connected`, `step_start`, `output`, `step_done`, `done`, `error`
- 独立通路，不改动 Session 状态机
- 内存字典 `_pipeline_executions` 管理执行上下文

**当前代码**：
- `src/api/routes/pipeline.py` — 只有 `POST /pipeline` (预览) 和 `POST /pipeline/execute` (触发)
- `src/api/websocket/` — 只有 `chat.py` 和 `execute.py`，没有 `pipeline_execute.py`
- 前端 `api/pipeline.ts` — 只有 `previewPipeline()` 和 `executePipeline()`，都是 HTTP

**建议**：如果 Pipeline 功能已上线且用户反馈执行超时，需要按 plan 补全 WebSocket。

---

### 问题 3：前端存在未使用的 HTTP fallback（可清理）

**`frontend/src/api/session.ts` 中的 `chatQuestion()`**：

```typescript
export async function chatQuestion(...) {
  const resp = await apiClient.post(`/session/${sessionId}/chat`, { input })
  return resp.data
}
```

前端不再调用此函数（已改为 WebSocket），但代码仍保留。建议：
- **保留**：作为 WebSocket 不可用时降级方案（需要实现 fallback 逻辑）
- **删除**：如果确定不再使用，应删除以避免维护负担

**`backend POST /session/{id}/chat` 端点**：

后端仍然实现了 HTTP 版本的 `chat_question`。可以保留作为 API 兼容性和测试用途。

---

## 三、接口设计原则确认

根据 plan-ux.md，协议选择的设计原则如下：

| 场景 | 协议 | 理由 |
|------|------|------|
| 状态流转（意图匹配、参数提交、模板锁定） | HTTP REST | 请求-响应，即时返回完整 SessionSnapshot |
| 数据查询（模板列表、详情） | HTTP REST | 纯数据查询，无实时性要求 |
| **Q&A 对话** | **WebSocket** | LLM 流式输出需要逐块推送 |
| **脚本执行日志** | **WebSocket** | subprocess stdout/stderr 需要逐行实时推送 |
| **Pipeline 执行日志** | **WebSocket** | 同脚本执行，且需要步骤级语义 |
| 模板生成/校验/保存 | HTTP REST | 同步计算，无需流式 |
| 执行环境验证 | HTTP REST | 同步验证，即时返回 |

**当前实现 vs 设计原则对比**：

| 场景 | 设计原则 | 实际实现 | 状态 |
|------|---------|---------|------|
| Q&A 对话 | WebSocket | ~~HTTP~~ → 已修复为 WebSocket | ✅ |
| 脚本执行 | WebSocket | WebSocket | ✅ |
| Pipeline 执行 | WebSocket | 只有 HTTP | ❌ |

---

## 四、建议行动项

### 高优先级

1. **验证 Q&A WebSocket 修复** — 重启前端，测试有模板/无模板两种场景的 Q&A，确认不再超时，且能看到流式"打字"效果

2. **实现 Pipeline 执行 WebSocket**（如 Pipeline 功能已启用）
   - 后端：新增 `src/api/websocket/pipeline_execute.py`
   - 后端：在 `main.py` 中注册 `/ws/pipeline-execute/{execution_id}` 路由
   - 前端：修改 Pipeline 页面，执行时连接 WebSocket 而非等待 HTTP 响应
   - 参考：现有 `execute.py` 的 subprocess 流式读取模式

### 中优先级

3. **清理废弃代码**
   - 前端 `api/session.ts` 中的 `chatQuestion()` 函数（如确定不再需要 HTTP fallback）
   - 或者保留并添加注释说明这是 fallback API

4. **统一错误处理**
   - 当前前端 catch 块显示固定消息"处理失败，请重试"
   - 建议改为显示后端返回的具体错误信息，方便排查

### 低优先级

5. **增加前端请求超时配置**
   - 即使 WebSocket 修复后，HTTP API 的超时配置（30秒）对于部分 LLM 调用仍可能不够
   - 建议将非流式 LLM 调用的超时增加到 60-120 秒，或实现可配置

---

## 五、附录：前后端文件映射

### 后端路由文件

| 文件 | 内容 |
|------|------|
| `src/api/routes/session.py` | Session 全生命周期 REST API |
| `src/api/routes/templates.py` | 模板查询 REST API |
| `src/api/routes/pipeline.py` | Pipeline 预览+触发 REST API |
| `src/api/routes/generator.py` | J2 模板生成 REST API |
| `src/api/routes/exec_env.py` | 执行环境 REST API |
| `src/api/websocket/chat.py` | Q&A WebSocket handler ✅ |
| `src/api/websocket/execute.py` | 脚本执行 WebSocket handler ✅ |
| `src/api/main.py` | FastAPI 应用工厂，注册所有路由 |

### 前端 API 文件

| 文件 | 内容 |
|------|------|
| `frontend/src/api/session.ts` | Session API 调用 |
| `frontend/src/api/templates.ts` | 模板 API 调用 |
| `frontend/src/api/pipeline.ts` | Pipeline API 调用 |
| `frontend/src/api/generator.ts` | 生成器 API 调用 |
| `frontend/src/api/execEnv.ts` | 执行环境 API 调用 |
| `frontend/src/api/health.ts` | 健康检查 API 调用 |
| `frontend/src/api/client.ts` | axios 实例配置 |
| `frontend/src/hooks/useWebSocket.ts` | WebSocket 通用 hook |

---

## 注

**注1**：`POST /session/{id}/chat` HTTP 端点后端仍然实现，可作为 WebSocket 不可用时降级方案。前端已改为 WebSocket，但 HTTP API 保留。

**注2**：Pipeline WebSocket 端点 (`/ws/pipeline-execute/{execution_id}`) 在 plan-pipeline-execute.md 中详细设计，但实际代码未实现。需要评估 Pipeline 功能是否已上线，再决定是否补全。
