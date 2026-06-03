# plan-pipeline-execute

| 项目 | 内容 |
|------|------|
| 版本 | v1.0.0 |
| 状态 | 草案 |
| 作者 | - |
| 日期 | 2026-05-30 |

---

## 1. 设计概述

### 1.1 模块职责

补全 Pipeline 多任务串行功能的**执行通路**。`plan-ux.md`（DC-UX-06）已定义 Pipeline 在前端的编排结构和后端的预览接口，但缺少从"合并脚本"到"流式执行"再到"结果反馈"的完整链路。本文档定义：

1. **合并脚本生成策略**：将多步骤脚本按 `&&` 链式合并，一步失败即中断
2. **Pipeline 执行 WebSocket**：独立于 Session 执行 WS 的新通路，支持分步骤实时日志推送
3. **前端 Pipeline 执行面板**：将 PipelinePage 的执行从 `alert` 升级为实时日志展示
4. **错误定位**：某步骤失败时，WS 推送失败步骤索引和 stderr，前端高亮对应步骤

### 1.2 所属架构层次

API 层（`api/`）+ 前端层（`frontend/`）。

- **不改动 `core/` 层**：Session 状态机保持单任务语义（DC-UX-06 锁定）
- **不改动 `cli/` 层**：Pipeline 为浏览器 UI 独占功能
- **复用 `templates/` 层**：`TemplateEngine.render()` 逐步骤渲染，复用现有安全校验

### 1.3 对应需求项

| 需求 ID | 需求描述 |
|:-------:|---------|
| UX-2 | Pipeline 多任务串行的可视化编辑和合并脚本生成 |
| F5 | 向用户完整展示脚本内容，要求明确确认后执行 |
| P2 | 先展后行：脚本预览 + 确认执行 |

---

## 2. 设计决策

### DC-0100: Pipeline 合并脚本采用 `&&` 链式执行

**决策**: 将 Pipeline 各步骤渲染后的命令行按 `&&` 运算符连接，生成单一可执行脚本。Windows 平台使用 cmd 的 `&&`，类 Unix 平台使用 bash 的 `&&`。

**理由**:
- GIS 数据处理步骤通常是**强顺序依赖**（如：转格式 → 重投影 → 切片），前一步失败时后续步骤无意义
- `&&` 是 shell 原生语义，失败时自动中断，无需额外进程管理逻辑
- 与单任务脚本的执行模型一致（都是一个 subprocess 执行一个脚本文件）

**合并规则**:

```
输入：[
  "ogr2ogr -f 'GeoJSON' 'roads.json' 'roads.shp'",
  "ogr2ogr -f 'GeoJSON' -t_srs 'EPSG:4326' 'roads_4326.json' 'roads.json'"
]

输出（Windows）:
  @echo off
  echo [Step 1/2] Shapefile 转 GeoJSON
  ogr2ogr -f "GeoJSON" "roads.json" "roads.shp" && \
  echo [Step 2/2] 重投影 && \
  ogr2ogr -f "GeoJSON" -t_srs "EPSG:4326" "roads_4326.json" "roads.json"
```

**平台差异**:

| 平台 | 头部 | 步骤分隔 | 步骤标记 |
|------|------|----------|----------|
| Windows | `@echo off` | `&&` + 换行 | `echo [Step N/M] 模板名` |
| Unix | `#!/bin/bash` + `set -e` | `&&` + 换行 | `echo "[Step N/M] 模板名"` |

**替代方案**:
- 独立执行每步（已否决）：失败时继续后续步骤，对 GIS 链式处理无意义，且增加状态跟踪复杂度
- Python 侧逐个启动 subprocess（已否决）：需要维护中间进程状态，与现有 WS 执行模型差异大

---

### DC-0101: Pipeline 执行状态使用内存字典，不进入 SessionManager

**决策**: Pipeline 执行定义（步骤列表 + 参数）通过 POST `/pipeline/execute` 提交后，后端存入全局内存字典 ` _pipeline_executions: dict[str, PipelineExecution]`，WebSocket 连接时按 `execution_id` 查取。不写入 `SessionManager`。

**理由**:
- Pipeline 是**瞬态执行上下文**，非持久会话状态，不需要跨连接保持
- SessionManager 承载的是单任务状态机，Pipeline 数据结构与之不兼容
- 内存字典实现简单，无需改 `core/models.py` 或 `api/dependencies.py` 的 SessionManager

**生命周期**:

```
POST /pipeline/execute ──→ 生成 execution_id ──→ 存入 _pipeline_executions
                              │
                              ▼
                     WS /ws/pipeline-execute/{execution_id}
                              │
                              ├──→ 连接成功：查字典取定义，开始执行
                              ├──→ 执行完成：从字典移除
                              └──→ 连接断开/超时：从字典移除
```

**数据结构**:

```python
@dataclass
class PipelineExecution:
    execution_id: str
    steps: list[PipelineStepRequest]      # 原始步骤（autoLinks 已应用）
    created_at: float                     # time.time()，用于过期清理
    workspace_root: str
```

**过期清理**: 启动后台 asyncio Task，每 60 秒扫描一次，移除 `created_at` 超过 10 分钟未消费的定义。

---

### DC-0102: Pipeline WebSocket 协议扩展步骤级语义

**决策**: Pipeline 执行 WebSocket 在单任务 WS 协议基础上，增加 `step_start` / `step_done` 帧类型，使前端能展示步骤级进度。

**协议帧类型**:

| 帧类型 | 方向 | 字段 | 说明 |
|--------|------|------|------|
| `connected` | S→C | `execution_id` | 连接确认 |
| `step_start` | S→C | `step`, `name`, `total` | 某步骤开始执行 |
| `output` | S→C | `line`, `stream`, `step` | 输出行（携带所属步骤索引） |
| `step_done` | S→C | `step`, `success` | 某步骤完成（成功/失败） |
| `done` | S→C | `success`, `failed_step?`, `error?` | 全部完成或中断 |
| `error` | S→C | `message` | 非执行错误（如脚本渲染失败） |

**理由**:
- 前端 PipelinePage 需要在日志区旁展示"步骤进度条"（如 2/4 完成）
- 失败后需要定位到具体步骤卡片高亮，需要步骤索引
- `stream` 字段保留（stdout/stderr），便于与单任务 WS 日志组件复用

---

### DC-0103: 错误报告定位到失败步骤，不提供 LLM 自动修复

**决策**: Pipeline 执行失败时，WS 返回 `failed_step` 索引和该步骤的 stderr。前端将该步骤卡片标记为错误态。不调用 `analyze_execution_error()` 进行 LLM 诊断。

**理由**:
- Pipeline 错误场景比单任务复杂（可能是前一步输出格式不对导致后一步失败），LLM 诊断上下文难以精确构建
- 先提供**快速定位**能力，用户手动检查失败步骤参数即可解决大部分问题
- 保留未来扩展空间：可在 `step_done` / `done` 帧中增加 `diagnosis` 可选字段

**前端表现**:

```
步骤 1 ✓ Shapefile 转 GeoJSON
步骤 2 ✓ 重投影
步骤 3 ✗ 生成切片        ← 卡片边框变红，展开显示 stderr
步骤 4 ○ 瓦片验证         ← 灰色（未执行，因 && 链中断）
```

---

### DC-0104: 复用单任务 WS 的 subprocess 执行模型，不换实现机制

**决策**: Pipeline 执行 WS 内部仍使用 `asyncio.create_subprocess_exec` 启动合并脚本，复用 `handle_execute_websocket` 的流式读取逻辑。不改为每步独立 subprocess。

**理由**:
- `&&` 链已将多步骤合并为单脚本，天然适配单 subprocess 模型
- 流式读取 stdout/stderr 的逻辑完全一致，提取为共用 helper 即可
- 超时控制（300 秒）按整 Pipeline 计算，不按单步骤拆分

---

## 3. 接口定义

### 3.1 REST API（变更）

```python
# api/routes/pipeline.py

@router.post("/pipeline/execute", response_model=PipelineExecutionTriggerResponse, status_code=202)
async def execute_pipeline(request: PipelineRequest) -> PipelineExecutionTriggerResponse:
    """提交 Pipeline 执行，存入内存字典，返回 execution_id。

    实际执行通过 WebSocket /ws/pipeline-execute/{execution_id} 进行。
    """
    # 1. 应用 autoLinks、验证每步模板和参数（与 preview 相同）
    # 2. 生成 execution_id，构建 PipelineExecution 存入内存字典
    # 3. 返回 execution_id + 合并后的脚本预览（前端 WS 连接前可展示）
```

**变更点**: 原 `execute_pipeline` 只返回 `execution_id`，现增加返回 `script`（合并后的脚本预览），方便前端在 WS 连接前展示最终脚本内容。

**响应模型**:

```python
class PipelineExecutionTriggerResponse(BaseModel):
    execution_id: str
    script: str          # 新增：合并后的完整脚本
    message: str
```

### 3.2 WebSocket 接口（新增）

```python
# api/main.py

@app.websocket("/ws/pipeline-execute/{execution_id}")
async def pipeline_execute_websocket(websocket: WebSocket, execution_id: str) -> None:
    """Pipeline 执行实时日志 WebSocket。

    协议见 DC-0102。
    """
    await handle_pipeline_execute_websocket(websocket, execution_id)
```

```python
# api/websocket/pipeline_execute.py

async def handle_pipeline_execute_websocket(
    websocket: WebSocket, execution_id: str
) -> None:
    """处理 Pipeline 执行 WebSocket 连接。

    流程：
        1. 从内存字典查取 PipelineExecution
        2. 逐步骤渲染脚本，合并为 && 链脚本
        3. 写入临时脚本文件
        4. 启动 subprocess，流式推送输出
        5. 每步开始/结束发送 step_start / step_done
        6. 全部完成或失败发送 done
    """
```

### 3.3 核心数据结构

```python
# api/routes/pipeline.py

@dataclass
class PipelineExecution:
    """Pipeline 执行定义（内存存储）。"""
    execution_id: str
    steps: list[PipelineStepRequest]
    created_at: float
    workspace_root: str

# 全局内存字典（模块级变量，非持久化）
_pipeline_executions: dict[str, PipelineExecution] = {}
```

```typescript
// frontend/src/types/index.ts（扩展）

interface PipelineExecutionResponse {
  execution_id: string
  script: string
  message: string
}

// WebSocket 帧类型（ discriminated union ）
interface WSPipelineConnected {
  type: 'connected'
  execution_id: string
}

interface WSPipelineStepStart {
  type: 'step_start'
  step: number
  name: string
  total: number
}

interface WSPipelineOutput {
  type: 'output'
  line: string
  stream: 'stdout' | 'stderr'
  step: number
}

interface WSPipelineStepDone {
  type: 'step_done'
  step: number
  success: boolean
}

interface WSPipelineDone {
  type: 'done'
  success: boolean
  failed_step?: number
  error?: string
}

type PipelineWSMessage =
  | WSPipelineConnected
  | WSPipelineStepStart
  | WSPipelineOutput
  | WSPipelineStepDone
  | WSPipelineDone
```

---

## 4. 模块变更清单

### 4.1 后端

| 文件 | 变更类型 | 内容 |
|------|----------|------|
| `api/routes/pipeline.py` | 修改 | `execute_pipeline` 返回模型增加 `script`；新增 `_pipeline_executions` 字典和 `PipelineExecution`；新增 `_merge_pipeline_script()` helper |
| `api/websocket/pipeline_execute.py` | **新增** | Pipeline 执行 WS handler：查字典、合并脚本、subprocess 执行、步骤级帧推送 |
| `api/websocket/__init__.py` | 修改 | 导出 `handle_pipeline_execute_websocket` |
| `api/main.py` | 修改 | 注册 `/ws/pipeline-execute/{execution_id}` 路由 |

### 4.2 前端

| 文件 | 变更类型 | 内容 |
|------|----------|------|
| `frontend/src/api/pipeline.ts` | 修改 | `executePipeline` 返回类型更新为 `PipelineExecutionResponse` |
| `frontend/src/types/index.ts` | 修改 | 新增 `PipelineExecutionResponse`、`PipelineWSMessage` 等类型 |
| `frontend/src/hooks/useWebSocket.ts` | 修改 | 扩展或新增 `usePipelineExecuteWebSocket`，支持 Pipeline WS 协议解析 |
| `frontend/src/pages/PipelinePage.tsx` | 修改 | 执行后连接 WS，替换 alert；右侧面板增加实时日志区和步骤进度指示 |

---

## 5. 执行时序

```
前端 PipelinePage                          后端 API
     │                                         │
     │ POST /pipeline/execute                  │
     │ { steps, autoLinks }                    │
     │────────────────────────────────────────>│
     │                                         │ 1. apply_auto_links
     │                                         │ 2. validate each step
     │                                         │ 3. merge_script (&& chain)
     │<────────────────────────────────────────│
     │ { execution_id, script }                │
     │                                         │ 4. store in _pipeline_executions
     │                                         │
     │ WS /ws/pipeline-execute/{execution_id}  │
     │────────────────────────────────────────>│
     │                                         │ 5. lookup PipelineExecution
     │<─ { type: "connected" } ─────────────────│
     │                                         │ 6. write merged script to temp file
     │                                         │ 7. start subprocess
     │                                         │
     │<─ { type: "step_start", step:0 } ────────│
     │<─ { type: "output", line:"...", step:0 } │
     │<─ { type: "step_done", step:0 } ─────────│
     │<─ { type: "step_start", step:1 } ────────│
     │<─ { type: "output", line:"...", step:1 } │
     │<─ { type: "step_done", step:1 } ─────────│
     │                                         │
     │<─ { type: "done", success:true } ────────│ 8. all steps succeeded
     │                                         │ 9. remove from _pipeline_executions
```

**失败时序**（步骤 1 失败）：

```
     │<─ { type: "step_start", step:0 } ────────│
     │<─ { type: "output", line:"...", step:0 } │
     │<─ { type: "output", line:"ERR", step:0, stream:"stderr" }
     │<─ { type: "done", success:false,          │
     │     failed_step:0, error:"stderr内容" } ───│
```

---

## 6. 错误处理

| 场景 | 行为 |
|------|------|
| 内存字典中找不到 execution_id | WS 关闭，code=1008，reason="Invalid execution" |
| 某步骤脚本渲染失败 | 发送 `{"type":"error","message":"..."}`，关闭 WS |
| 某步骤执行返回非 0 | `&&` 链中断，发送 `done`（`success:false`，`failed_step` 指向该步骤） |
| subprocess 启动失败 | 发送 `error`，关闭 WS |
| 超时（300s） | kill subprocess，发送 `done`（`success:false`，`error:"timeout"`） |
| 客户端断开 | kill subprocess，清理字典条目 |
| 字典条目过期（10min 未消费） | 后台任务自动移除 |

---

## 7. 安全考量

- **脚本合并后仍过安全校验**：每步骤 individually 渲染时已通过 `ScriptSecurityChecker`（DC-0052），合并只是添加 `echo` 和 `&&`，不引入新的危险模式
- **临时脚本文件写入 workspace**：与单任务一致，文件名含 `pipeline_` 前缀 + timestamp，执行后保留（便于用户事后查看完整脚本）
- **内存字典大小限制**：Pipeline 定义只存步骤索引和参数字符串，不含二进制数据，数量受限于并发连接数

---

## 8. 测试策略

| 测试项 | 类型 | 说明 |
|--------|------|------|
| `_merge_pipeline_script` 生成 `&&` 链 | 单元测试 | Windows / Unix 双平台输出验证 |
| `_merge_pipeline_script` 步骤标记 | 单元测试 | 验证 `echo [Step N/M]` 插入位置正确 |
| `execute_pipeline` 存入字典 | 单元测试 | 验证 202 响应和字典条目存在 |
| `handle_pipeline_execute_websocket` 成功流 | 单元测试 | mock subprocess，验证帧序列 |
| `handle_pipeline_execute_websocket` 失败流 | 单元测试 | mock subprocess 返回非 0，验证 `failed_step` |
| 字典过期清理 | 单元测试 | mock 时间，验证过期条目被移除 |
| 前端 `usePipelineExecuteWebSocket` | 组件测试 | 验证 WS 消息解析和状态更新 |

---

## 9. 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.0.0 | 2026-05-30 | 初版，定义 Pipeline 执行合并脚本、独立 WS 通路、步骤级错误定位 |
