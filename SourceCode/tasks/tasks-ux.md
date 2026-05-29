# 浏览器 UI 模块实现任务清单

> 基于 `plan-ux.md` (DC-UX-01 ~ DC-UX-07)
> 前置依赖：core 层（T-CORE-01 ~ T-CORE-05）、llm 层、templates 层、cli 层已全部完成
> 创建日期: 2026-05-29

---

## 模块总览

Plan-UX 实现 GIS Agent 的浏览器交互层，包含前端（React + TypeScript + Vite）和 API 后端（FastAPI）两部分。CLI 层完整保留，与 API 层并行存在。

| 组件 | 文件 | 职责 | 设计决策 |
|------|------|------|----------|
| `FastAPIApp` | `api/main.py` | ASGI 应用实例、CORS、路由注册、静态文件托管 | DC-UX-01 |
| `Dependencies` | `api/dependencies.py` | FastAPI Depends：Session 获取、Workspace 单例注入 | DC-UX-03 |
| `SessionRoutes` | `api/routes/session.py` | 会话状态流转 REST API | DC-UX-03 |
| `TemplateRoutes` | `api/routes/templates.py` | 模板查询 REST API | DC-UX-02 |
| `PipelineRoutes` | `api/routes/pipeline.py` | Pipeline 合并脚本 REST API | DC-UX-06 |
| `GeneratorRoutes` | `api/routes/generator.py` | J2 模板生成器 REST API | DC-UX-07 |
| `ChatWebSocket` | `api/websocket/chat.py` | Q&A 流式对话 WebSocket | DC-UX-04 |
| `ExecuteWebSocket` | `api/websocket/execute.py` | 脚本执行实时日志 WebSocket | DC-UX-05 |
| `MainPage` | `frontend/src/pages/MainPage.tsx` | 主应用页面（三栏布局 + 状态机映射） | DC-UX-02 |
| `GeneratorPage` | `frontend/src/pages/GeneratorPage.tsx` | 模板生成器子页面 | DC-UX-07 |

**依赖关系**：
```
frontend --(HTTP/WebSocket)--> api/routes/*, api/websocket/*
     |
     v
api/main.py --> api/dependencies.py --> core/*, llm/*, templates/*
     |
     v
cli/ (并行存在，互不依赖)
```

---

## T-UX-01: FastAPI 骨架 + 依赖注入

**设计依据**: plan-ux §3, §6, §7 (DC-UX-01, DC-UX-03)

### 红 — 编写测试

- [ ] `tests/unit/test_api_main.py`:
  - `test_app_instance_created`: `create_app()` 返回 FastAPI 实例
  - `test_cors_middleware_configured`: 允许 `http://localhost:5173`（Vite 开发服务器）
  - `test_routes_registered`: `/api/session`、`/api/templates`、`/api/pipeline`、`/api/generator` 路由存在
  - `test_health_check`: `GET /health` 返回 `{"status": "ok"}`
  - `test_static_files_mounted`: `/` 请求被 static 中间件处理
  - `test_404_unknown_route`: 未知路径返回 404

- [ ] `tests/unit/test_api_dependencies.py`:
  - `test_get_session_manager_returns_singleton`: 多次调用返回同一个 SessionManager
  - `test_get_workspace_returns_singleton`: 多次调用返回同一个 Workspace 实例
  - `test_get_registry_returns_scanned_templates`: Registry 含扫描到的模板
  - `test_get_session_or_404_found`: 存在 session_id 返回 Session
  - `test_get_session_or_404_not_found`: 不存在 session_id 返回 404

### 绿 — 实现代码

- [ ] `api/__init__.py`: 暴露 `create_app`
- [ ] `api/main.py`:
  - `create_app() -> FastAPI`: 创建应用实例
  - 注册 CORS：`allow_origins=["http://localhost:5173"]`
  - 注册路由：`/api/session`、`/api/templates`、`/api/pipeline`、`/api/generator`
  - 注册 WebSocket：`/ws/chat/{session_id}`、`/ws/execute/{session_id}`
  - 生产模式挂载 static：`app.mount("/", StaticFiles(directory="../frontend/dist", html=True), name="static")`
  - `GET /health` 健康检查端点
  - `main()` 入口：`uvicorn.run(app, host="0.0.0.0", port=8000)`
- [ ] `api/dependencies.py`:
  - `get_session_manager() -> SessionManager`: 维护 session_id → Session 映射的单例
  - `get_workspace() -> Workspace`: 复用 `core/workspace.py` 单例
  - `get_registry() -> TemplateRegistry`: 复用扫描结果
  - `get_validator() -> ParamValidator`: 复用已有实例
  - `get_template_engine() -> TemplateEngine`: 复用已有实例
  - `get_llm_client() -> LLMClient`: 复用已有实例
  - `get_prompt_builder() -> PromptBuilder`: 复用已有实例
  - `get_session_or_404(session_id, session_manager) -> Session`: 不存在时抛 HTTPException(404)

### 重构

- [ ] 确认 `api/` 不 import `cli/` 任何模块（DEP-7 合规）
- [ ] 确认依赖注入函数签名与 FastAPI `Depends` 兼容
- [ ] 确认生产模式 static 路径解析正确（相对 `SourceCode/src/api/main.py`）

**涉及文件**: `api/__init__.py`, `api/main.py`, `api/dependencies.py`, `tests/unit/test_api_main.py`, `tests/unit/test_api_dependencies.py`

---

## T-UX-02: Session REST API

**设计依据**: plan-ux §3.1, §4.1 (DC-UX-02, DC-UX-03)

### 红 — 编写测试

- [ ] `tests/unit/test_api_session.py`:

**创建会话**:
  - `test_create_session`: `POST /api/session` → 返回 session_id，state=`IDLE`
  - `test_create_session_with_workspace`: `POST /api/session?workspace=/data` → 使用指定工作空间

**意图处理**:
  - `test_process_intent_idle`: `POST /api/session/{id}/intent` {"input":"shp转geojson"} → state=`INTENT_CONFIRM` 或 `PARAM_COLLECT`，含候选模板
  - `test_process_intent_no_match`: 无匹配输入 → state=`IDLE`，response 提示无法识别
  - `test_process_intent_session_not_found`: 无效 session_id → 404

**模板锁定**:
  - `test_lock_template`: `POST /api/session/{id}/lock` {"template_id":"shp2geojson"} → state=`PARAM_COLLECT`
  - `test_lock_template_invalid_id`: 无效 template_id → 400

**参数提交**:
  - `test_submit_params_complete`: 完整参数 → state=`SCRIPT_PREVIEW`，script_preview 非空
  - `test_submit_params_incomplete`: 缺失必填参数 → state=`PARAM_COLLECT`，missing_params 列出缺失字段
  - `test_submit_params_validation_error`: 参数校验失败（如 CRS 格式错误）→ 400，含具体错误

**执行触发**:
  - `test_execute_script_triggers`: `POST /api/session/{id}/execute` → 返回 execution_id，状态 202 Accepted（实际执行走 WebSocket）
  - `test_execute_dry_run`: `?dry_run=true` → 返回预览信息，不触发执行

**清空会话**:
  - `test_clear_session`: `POST /api/session/{id}/clear` → state=`IDLE`，task_context 清空

### 绿 — 实现代码

- [ ] `api/routes/__init__.py`
- [ ] `api/routes/session.py`:
  - `router = APIRouter(prefix="/api/session", tags=["session"])`
  - `SessionManager` 类：内存字典 `sessions: dict[str, Session]`，线程安全（asyncio.Lock）
    - `create_session(workspace: Optional[str] = None) -> Session`: 创建新 Session，初始化 Workspace
    - `get_session(session_id: str) -> Optional[Session]`
    - `update_session(session: Session)`: 保存更新后的 Session（不可变替换）
    - `clear_session(session_id: str)`: 重置为 IDLE
  - `POST /session`: 调用 `session_manager.create_session()` → `SessionResponse`
  - `POST /session/{session_id}/intent`: 调用 `SessionProcessor._handle_idle()` 逻辑 → `SessionResponse`
  - `POST /session/{session_id}/lock`: 设置 template_id → `PARAM_COLLECT` → `SessionResponse`
  - `POST /session/{session_id}/params`: 调用 `ParamValidator.validate_all()` + `TemplateEngine.render()` → `SessionResponse`
  - `POST /session/{session_id}/execute`: 生成 execution_id，返回 202 → 实际执行由前端通过 WebSocket 连接完成
  - `POST /session/{session_id}/clear`: 调用 `session_manager.clear_session()`
- [ ] Pydantic 模型：
  - `SessionResponse`: session_id, state, task_context, script_preview, error_context, history
  - `IntentRequest`: input: str
  - `LockRequest`: template_id: str
  - `ParamsRequest`: params: dict[str, str]
  - `ExecutionTriggerResponse`: execution_id: str, message: str

### 重构

- [ ] 确认 SessionManager 使用不可变替换（Session 是 frozen dataclass）
- [ ] 确认所有响应模型与前端 `SessionSnapshot` TypeScript 类型对齐
- [ ] 确认错误响应统一使用 FastAPI `HTTPException` 含 detail 字段

**涉及文件**: `api/routes/__init__.py`, `api/routes/session.py`, `tests/unit/test_api_session.py`

---

## T-UX-03: Templates REST API

**设计依据**: plan-ux §3.1 (DC-UX-02)

### 红 — 编写测试

- [ ] `tests/unit/test_api_templates.py`:
  - `test_list_templates`: `GET /api/templates` → 返回所有模板列表（含 id, name, description, category, tags）
  - `test_list_templates_empty`: 无模板时返回空列表
  - `test_get_template_detail`: `GET /api/templates/shp2geojson` → 返回完整 TemplateDetail（params, concepts, notes, common_errors, seealso）
  - `test_get_template_not_found`: 无效 template_id → 404
  - `test_template_detail_param_defs`: 返回的 params 含 name, type, required, description, default
  - `test_template_detail_concepts`: 返回的 concepts 含 term, explanation

### 绿 — 实现代码

- [ ] `api/routes/templates.py`:
  - `router = APIRouter(prefix="/api/templates", tags=["templates"])`
  - `GET /templates`: 调用 `registry.list_templates()` → `List[TemplateDef]`
  - `GET /templates/{template_id}`: 调用 `registry.get_template()` + 组装 TemplateDetail → `TemplateDetail`
- [ ] Pydantic 模型：
  - `TemplateDefResponse`: id, name, description, category, tool_source, tags
  - `ParamDefResponse`: name, type, required, description, default
  - `ConceptItemResponse`: term, explanation
  - `CommonErrorItemResponse`: error_text, cause, fix
  - `TemplateDetailResponse`: 继承 TemplateDefResponse + params, concepts, notes, common_errors, seealso

### 重构

- [ ] 确认响应模型字段名与前端 `TemplateDef` / `TemplateDetail` TypeScript 接口一致
- [ ] 确认 category 枚举值与前端对齐：`vector` | `raster` | `general` | `database`

**涉及文件**: `api/routes/templates.py`, `tests/unit/test_api_templates.py`

---

## T-UX-04: Chat WebSocket

**设计依据**: plan-ux §3.2 (DC-UX-04)

### 红 — 编写测试

- [ ] `tests/unit/test_api_ws_chat.py`:
  - `test_chat_websocket_connect`: 客户端连接 `ws://localhost:8000/ws/chat/{session_id}` → 成功 accept
  - `test_chat_stream_response`: 发送消息后，服务端逐片推送 LLM 回复 → 前端收到多个 text 帧
  - `test_chat_done_signal`: 流结束后收到 `{"type": "done"}` JSON 消息
  - `test_chat_invalid_session`: 无效 session_id → 连接被拒绝（close code 1008）
  - `test_chat_disconnect_cleanup`: 客户端断开连接后，服务端释放资源（不抛异常）

### 绿 — 实现代码

- [ ] `api/websocket/__init__.py`
- [ ] `api/websocket/chat.py`:
  - `ChatWebSocketHandler` 类:
    - `async def handle(websocket: WebSocket, session_id: str, session_manager, llm_client, prompt_builder)`
    - `await websocket.accept()`
    - 循环接收前端消息
    - 调用 `llm.answer_question()`，将 `on_chunk` 回调接入 `websocket.send_text(chunk)`
    - 流结束后发送 `{"type": "done"}`
    - 异常处理：捕获后发送 `{"type": "error", "message": str(e)}`
- [ ] `api/routes/websocket.py`（或直接在 main.py 中注册）:
  - `@app.websocket("/ws/chat/{session_id}")`

### 重构

- [ ] 确认 `on_chunk` 回调在异步上下文中正确工作
- [ ] 确认 WebSocket 连接异常断开时不影响其他 session
- [ ] 确认 LLM 调用复用 `llm/` 模块（CODE-3 合规）

**涉及文件**: `api/websocket/__init__.py`, `api/websocket/chat.py`, `tests/unit/test_api_ws_chat.py`

---

## T-UX-05: Execute WebSocket

**设计依据**: plan-ux §3.2 (DC-UX-05)

### 红 — 编写测试

- [ ] `tests/unit/test_api_ws_execute.py`:
  - `test_execute_websocket_connect`: 客户端连接 `ws://localhost:8000/ws/execute/{session_id}` → 成功 accept
  - `test_execute_stream_output`: 服务端启动 mock subprocess，逐行推送 stdout → 前端收到多行输出
  - `test_execute_done_signal`: 执行完成后收到 `{"type": "done", "success": true, "output_path": "..."}`
  - `test_execute_failure_signal`: 执行失败（exit code != 0）→ `{"type": "done", "success": false, "error": "..."}`
  - `test_execute_timeout`: 超时（>300s）→ 强制终止进程，发送 `{"type": "done", "success": false, "error": "timeout"}`
  - `test_execute_invalid_session`: 无效 session_id → 连接被拒绝
  - `test_execute_no_script_preview`: session 不在 SCRIPT_PREVIEW 状态 → 发送 error 后关闭

### 绿 — 实现代码

- [ ] `api/websocket/execute.py`:
  - `ExecuteWebSocketHandler` 类:
    - `async def handle(websocket: WebSocket, session_id: str, session_manager, script_executor)`
    - `await websocket.accept()`
    - 从 session 获取 `script_preview`
    - 使用 `asyncio.create_subprocess_exec()` 或线程池中的 `subprocess.Popen()`
    - 逐行读取 stdout/stderr，通过 `websocket.send_text()` 推送
    - 完成/失败后发送 `{"type": "done", ...}`
    - 超时控制：300 秒，超时后 `process.kill()`
- [ ] `api/routes/websocket.py`:
  - `@app.websocket("/ws/execute/{session_id}")`

### 重构

- [ ] 确认 subprocess 在异步上下文中不阻塞事件循环（使用线程池或 asyncio subprocess）
- [ ] 确认超时后进程被正确终止（避免僵尸进程）
- [ ] 确认执行日志格式与 CLI 模式一致

**涉及文件**: `api/websocket/execute.py`, `api/routes/websocket.py`, `tests/unit/test_api_ws_execute.py`

---

## T-UX-06: Pipeline REST API

**设计依据**: plan-ux §3.1, §4.2 (DC-UX-06)

### 红 — 编写测试

- [ ] `tests/unit/test_api_pipeline.py`:
  - `test_preview_pipeline_single_step`: 单步骤 Pipeline → 返回与直接渲染相同的脚本
  - `test_preview_pipeline_two_steps`: 两步 Pipeline（shp→geojson→重投影）→ 返回合并脚本，含两个命令
  - `test_preview_pipeline_auto_link`: 步骤间自动关联（step1 output → step2 input）→ 参数正确传递
  - `test_preview_pipeline_invalid_template`: 含无效 template_id → 400
  - `test_preview_pipeline_missing_param`: 必填参数缺失 → 400
  - `test_execute_pipeline`: `POST /api/pipeline/execute` → 返回 execution_id（实际走 Execute WebSocket）

### 绿 — 实现代码

- [ ] `api/routes/pipeline.py`:
  - `router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])`
  - `POST /api/pipeline`: `preview_pipeline(request)`
    - 验证每个 step 的 template_id 存在
    - 验证每个 step 的参数
    - 应用 autoLinks 关联规则
    - 对每个 step 调用 `TemplateEngine.render()`
    - 合并为多步骤脚本（`\n\n` 分隔）
    - 返回 `ScriptPreviewResponse`
  - `POST /api/pipeline/execute`: 生成 execution_id，返回 202（实际执行走 WebSocket）
- [ ] Pydantic 模型：
  - `PipelineStepRequest`: order, template_id, params
  - `DataLinkRequest`: fromStep, fromParam, toStep, toParam
  - `PipelineRequest`: steps, autoLinks
  - `ScriptPreviewResponse`: script: str, steps: list[StepPreview]
  - `StepPreview`: order, template_id, template_name, params

### 重构

- [ ] 确认 Pipeline 合并脚本经过 `ScriptSecurityChecker` 安全校验
- [ ] 确认 autoLinks 的循环依赖检测（fromStep → toStep 不能形成环）
- [ ] 确认 Pipeline 预览与单任务 SCRIPT_PREVIEW 格式一致

**涉及文件**: `api/routes/pipeline.py`, `tests/unit/test_api_pipeline.py`

---

## T-UX-07: Generator REST API

**设计依据**: plan-ux §3.1 (DC-UX-07)

### 红 — 编写测试

- [ ] `tests/unit/test_api_generator.py`:
  - `test_generate_template`: `POST /api/generator/generate` 含文档文本和配置 → 返回 GeneratedTemplate（template_id, name, description, body, params）
  - `test_validate_template_safe`: 合法模板 → `{"valid": true}`
  - `test_validate_template_unsafe`: 含危险模式（如 `{{ cmd \| safe }}`）→ `{"valid": false, "errors": [...]}`
  - `test_save_template`: `POST /api/generator/save` → 保存到 `data/templates/` 目录，返回保存路径
  - `test_save_template_overwrite_protection`: 同名模板 → 409 或自动重命名
  - `test_generate_invalid_input`: 空文档 → 400

### 绿 — 实现代码

- [ ] `api/routes/generator.py`:
  - `router = APIRouter(prefix="/api/generator", tags=["generator"])`
  - `POST /api/generator/generate`: 调用 `scripts/generate/generator.py` 的生成逻辑（或内联简化版）
  - `POST /api/generator/validate`: 调用 `templates.engine.ScriptSecurityChecker` 校验
  - `POST /api/generator/save`: 写入 `data/templates/` 目录，更新注册表
- [ ] Pydantic 模型：
  - `GenerateRequest`: document_text, config（category, tool_source 等）
  - `GeneratedTemplateResponse`: template_id, name, description, body, params, concepts, notes
  - `ValidateRequest`: body: str
  - `ValidationResultResponse`: valid, errors
  - `SaveRequest`: template_id, body, overwrite: bool = false
  - `SaveResponse`: saved_path: str

### 重构

- [ ] 确认生成器路由仅在开发模式下可用（环境变量控制）
- [ ] 确认保存的模板文件遵循 `.j2` 命名规范和注释头格式
- [ ] 确认保存后触发模板重新扫描（或手动刷新）

**涉及文件**: `api/routes/generator.py`, `tests/unit/test_api_generator.py`

---

## T-UX-08: 前端项目初始化

**设计依据**: plan-ux §5, §7 (DC-UX-01)

### 红 — 编写测试

- [ ] 验证项目 scaffold：
  - `frontend/package.json` 存在且含 `react`, `react-dom`, `typescript`, `vite` 依赖
  - `frontend/vite.config.ts` 配置了 `@/` 路径别名指向 `src/`
  - `frontend/tsconfig.json` 配置了严格模式
  - `frontend/src/main.tsx` 可编译通过（npm run build 成功）
  - `frontend/index.html` 引用 `src/main.tsx`

### 绿 — 实现代码

- [ ] 创建 `frontend/` 目录结构：
  ```
  frontend/
  ├── package.json
  ├── vite.config.ts
  ├── tsconfig.json
  ├── tsconfig.app.json
  ├── tsconfig.node.json
  ├── index.html
  ├── tailwind.config.js
  └── src/
      ├── main.tsx
      ├── App.tsx
      ├── api/
      ├── components/
      ├── hooks/
      ├── pages/
      └── types/
  ```
- [ ] `package.json`: 依赖 `react`, `react-dom`, `react-router-dom`, `typescript`, `vite`, `zustand`, `tailwindcss`, `axios`, `clsx`, `tailwind-merge`
- [ ] `vite.config.ts`: `@/` 别名、`port: 5173`、`proxy: { '/api': 'http://localhost:8000', '/ws': 'ws://localhost:8000' }`
- [ ] `tsconfig.json`: `strict: true`, `target: ES2020`, `moduleResolution: bundler`
- [ ] `tailwind.config.js`: content 包含 `src/**/*.{ts,tsx}`, theme 扩展
- [ ] `src/main.tsx`: ReactDOM.createRoot, BrowserRouter, StrictMode
- [ ] `src/App.tsx`: Routes 定义 `/` → MainPage, `/generator` → GeneratorPage

### 重构

- [ ] 确认开发时 Vite proxy 配置正确（API 请求转发到 FastAPI）
- [ ] 确认生产构建输出到 `frontend/dist/`（FastAPI static 挂载点）
- [ ] 确认 `frontend/` 被 `.gitignore` 忽略 `node_modules/` 和 `dist/`

**涉及文件**: `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/tailwind.config.js`, `frontend/index.html`, `frontend/src/main.tsx`, `frontend/src/App.tsx`, `.gitignore`

---

## T-UX-09: 前端类型定义 + API Client

**设计依据**: plan-ux §3.3 (DC-UX-03)

### 红 — 编写测试

- [ ] 类型检查通过：`npx tsc --noEmit` 在 `frontend/` 目录下零报错

### 绿 — 实现代码

- [ ] `frontend/src/types/index.ts`:
  ```typescript
  export type SessionState = 'IDLE' | 'INTENT_CONFIRM' | 'PARAM_COLLECT' | 'SCRIPT_PREVIEW' | 'EXECUTING' | 'ERROR_RECOVERY';

  export interface SessionSnapshot {
    session_id: string;
    state: SessionState;
    task_context: {
      template_id: string | null;
      template_name: string | null;
      params: Record<string, string>;
      missing_params: string[];
    };
    script_preview: string | null;
    error_context: ErrorContext | null;
    history: ChatMessage[];
  }

  export interface ChatMessage {
    role: 'user' | 'agent';
    content: string;
    type?: 'text' | 'cards' | 'script' | 'timeline' | 'error';
    meta?: Record<string, unknown>;
  }

  export interface TemplateDef {
    id: string;
    name: string;
    description: string;
    category: 'vector' | 'raster' | 'general' | 'database';
    tool_source: string;
    tags: string[];
  }

  export interface ParamDef {
    name: string;
    type: 'file_path' | 'crs' | 'string' | 'boolean' | 'integer';
    required: boolean;
    description: string;
    default?: string;
  }

  export interface TemplateDetail extends TemplateDef {
    params: ParamDef[];
    concepts: ConceptItem[];
    notes: string[];
    common_errors: CommonErrorItem[];
    seealso: string[];
  }
  ```
- [ ] `frontend/src/api/client.ts`: axios 实例，`baseURL: '/api'`, 统一错误处理
- [ ] `frontend/src/api/session.ts`:
  - `createSession(workspace?: string): Promise<SessionSnapshot>`
  - `processIntent(sessionId, input): Promise<SessionSnapshot>`
  - `lockTemplate(sessionId, templateId): Promise<SessionSnapshot>`
  - `submitParams(sessionId, params): Promise<SessionSnapshot>`
  - `executeScript(sessionId, dryRun?): Promise<{ execution_id: string }>`
  - `clearSession(sessionId): Promise<void>`
- [ ] `frontend/src/api/templates.ts`:
  - `listTemplates(): Promise<TemplateDef[]>`
  - `getTemplate(templateId): Promise<TemplateDetail>`
- [ ] `frontend/src/api/pipeline.ts`:
  - `previewPipeline(steps, autoLinks): Promise<{ script: string }>`
- [ ] `frontend/src/api/generator.ts`:
  - `generateTemplate(doc, config): Promise<GeneratedTemplate>`
  - `validateTemplate(body): Promise<{ valid: boolean }>`
  - `saveTemplate(template): Promise<{ saved_path: string }>`

### 重构

- [ ] 确认 TypeScript 类型与后端 Pydantic 模型字段名完全一致
- [ ] 确认 axios 拦截器统一处理 404/500 错误（toast 或 console.error）

**涉及文件**: `frontend/src/types/index.ts`, `frontend/src/api/client.ts`, `frontend/src/api/session.ts`, `frontend/src/api/templates.ts`, `frontend/src/api/pipeline.ts`, `frontend/src/api/generator.ts`

---

## T-UX-10: 前端布局 + 状态管理 (Zustand)

**设计依据**: plan-ux §5, §3.3 (DC-UX-02, DC-UX-03)

### 红 — 编写测试

- [ ] 类型检查 + 构建通过
- [ ] 手动验证：打开页面能看到三栏布局框架

### 绿 — 实现代码

- [ ] `frontend/src/hooks/useSession.ts`: Zustand store
  ```typescript
  interface SessionStore {
    sessionId: string | null;
    state: SessionState;
    taskContext: TaskContext | null;
    messages: ChatMessage[];
    lockedTemplateId: string | null;
    scriptPreview: string | null;
    isLoading: boolean;
    // actions
    setSession: (snapshot: SessionSnapshot) => void;
    addMessage: (msg: ChatMessage) => void;
    setLoading: (loading: boolean) => void;
    reset: () => void;
  }
  ```
- [ ] `frontend/src/components/Layout.tsx`: 三栏布局（左 280px 固定、中 flex、右 360px 固定）
- [ ] `frontend/src/components/TopBar.tsx`: Logo + 当前状态标签 + 工作区路径
- [ ] `frontend/src/pages/MainPage.tsx`:
  - 启动时 `createSession()` 初始化
  - 渲染 Layout
  - 根据 `state` 条件渲染 DetailPanel 内容

### 重构

- [ ] 确认 Zustand store 只做 UI 状态，不缓存后端 Session 全量数据（防止状态漂移）
- [ ] 确认 Layout 响应式：窗口缩小到 < 1024px 时右栏可折叠

**涉及文件**: `frontend/src/hooks/useSession.ts`, `frontend/src/components/Layout.tsx`, `frontend/src/components/TopBar.tsx`, `frontend/src/pages/MainPage.tsx`

---

## T-UX-11: 前端聊天区域 + WebSocket

**设计依据**: plan-ux §3.3, §3.2, §4.1 (DC-UX-02, DC-UX-04)

### 红 — 编写测试

- [ ] 类型检查 + 构建通过
- [ ] 手动验证：能发送消息、收到 LLM 流式回复

### 绿 — 实现代码

- [ ] `frontend/src/hooks/useWebSocket.ts`:
  ```typescript
  interface UseWebSocketOptions {
    url: string;
    onMessage: (data: string) => void;
    onOpen?: () => void;
    onClose?: () => void;
    onError?: (error: Event) => void;
  }
  ```
  - 自动重连（指数退避，最多 5 次）
  - `send(message: string)`
  - `close()`
- [ ] `frontend/src/components/ChatArea.tsx`:
  - 中栏主区域
  - 消息列表（滚动到底部）
  - 输入框 + 发送按钮
  - 根据 `state` 显示不同提示（如 PARAM_COLLECT 时提示"请在右栏填写参数"）
- [ ] `frontend/src/components/ChatMessage.tsx`:
  - 单条消息气泡
  - `type="text"`: 普通文本渲染
  - `type="cards"`: 渲染模板候选卡片列表（INTENT_CONFIRM 状态）
  - `type="script"`: 代码块高亮 + 复制按钮 + 执行/取消按钮（SCRIPT_PREVIEW 状态）
  - `type="error"`: 红色错误提示（ERROR_RECOVERY 状态）

### 重构

- [ ] 确认 WebSocket 在组件卸载时正确 close
- [ ] 确认流式输出期间输入框禁用（防止并发消息）
- [ ] 确认 ChatMessage 的卡片点击触发 `lockTemplate()`

**涉及文件**: `frontend/src/hooks/useWebSocket.ts`, `frontend/src/components/ChatArea.tsx`, `frontend/src/components/ChatMessage.tsx`

---

## T-UX-12: 前端模板卡片 + 参数表单

**设计依据**: plan-ux §3.3, §4.1, §5 (DC-UX-02)

### 红 — 编写测试

- [ ] 类型检查 + 构建通过
- [ ] 手动验证：
  - 左栏显示模板卡片列表
  - 点击卡片右栏显示参数表单
  - 填写参数后提交，聊天区显示脚本预览

### 绿 — 实现代码

- [ ] `frontend/src/components/TemplateCardList.tsx`:
  - 左栏模板卡片网格/列表
  - 按 category 分组（vector/raster/general/database）
  - 搜索过滤（按 name/description/tags 匹配）
  - 点击卡片 → `lockTemplate()` + 右栏展开参数表单
- [ ] `frontend/src/components/DetailPanel.tsx`:
  - 右栏容器
  - 根据 `state` 渲染不同内容：
    - `IDLE`: 显示模板详情（description, concepts, notes, common_errors）
    - `PARAM_COLLECT`: 显示 ParamForm
    - `SCRIPT_PREVIEW`: 显示 ScriptPreview
    - `EXECUTING`: 显示执行进度
- [ ] `frontend/src/components/ParamForm.tsx`:
  - 根据 `ParamDef[]` 动态生成表单字段
  - `file_path`: 文件路径输入 + 浏览按钮（后续可扩展为文件选择器）
  - `crs`: 文本输入（带 EPSG: 前缀提示）
  - `string`: 文本输入
  - `boolean`: 开关/复选框
  - `integer`: 数字输入
  - 必填字段标记红色星号
  - 提交按钮 → `submitParams()`
- [ ] `frontend/src/components/ScriptPreview.tsx`:
  - 代码块展示（语法高亮可选）
  - "执行"按钮（绿色）→ 触发 Execute WebSocket
  - "修改参数"按钮（灰色）→ 返回 PARAM_COLLECT
  - "取消"按钮 → `clearSession()` 返回 IDLE

### 重构

- [ ] 确认 ParamForm 默认值与 TemplateDef 中 `default` 字段一致
- [ ] 确认表单验证失败时显示具体错误信息（不提交到后端）

**涉及文件**: `frontend/src/components/TemplateCardList.tsx`, `frontend/src/components/DetailPanel.tsx`, `frontend/src/components/ParamForm.tsx`, `frontend/src/components/ScriptPreview.tsx`

---

## T-UX-13: 前端 Pipeline 组件

**设计依据**: plan-ux §4.2, §5 (DC-UX-06)

### 红 — 编写测试

- [ ] 类型检查 + 构建通过
- [ ] 手动验证：
  - 能添加多个 Pipeline 步骤
  - 步骤间显示数据流关联
  - 生成脚本按钮返回合并脚本

### 绿 — 实现代码

- [ ] `frontend/src/components/PipelineOverview.tsx`:
  - 横向时间线概览
  - 每个步骤为圆形节点，含序号和模板名称
  - 节点间连线表示执行顺序
  - 点击节点跳转到对应步骤编辑
- [ ] `frontend/src/components/PipelineStepCard.tsx`:
  - 纵向堆叠的任务卡片
  - 每张卡片含：模板名称、参数表单（复用 ParamForm）
  - 删除按钮、上移/下移按钮
  - 步骤间显示数据流指示（上一步 output → 下一步 input）
- [ ] `frontend/src/components/DataFlowIndicator.tsx`:
  - 步骤间的连接线和箭头
  - 显示关联参数名（如 `roads.shp → roads.json`）
- [ ] Pipeline 状态管理（扩展 useSession store）：
  - `pipelineSteps: PipelineStep[]`
  - `addStep(templateId)`, `removeStep(index)`, `moveStep(from, to)`
  - `generateScript(): Promise<string>` → 调用 `previewPipeline()`

### 重构

- [ ] 确认 Pipeline UI 与单任务 UI 状态互斥（不同时在主页面显示）
- [ ] 确认 Pipeline 步骤上限（如 10 步），防止无限添加

**涉及文件**: `frontend/src/components/PipelineOverview.tsx`, `frontend/src/components/PipelineStepCard.tsx`, `frontend/src/components/DataFlowIndicator.tsx`

---

## T-UX-14: 前端模板生成器页面

**设计依据**: plan-ux §5, §7 (DC-UX-07)

### 红 — 编写测试

- [ ] 类型检查 + 构建通过
- [ ] 手动验证：
  - 访问 `/generator` 显示生成器页面
  - 输入文档文本后能生成模板
  - 审查通过后能保存到 templates 目录

### 绿 — 实现代码

- [ ] `frontend/src/pages/GeneratorPage.tsx`:
  - 5 步向导 UI：
    1. **文档输入**: 大文本框粘贴 GDAL HTML 文档内容
    2. **配置**: 选择 category、tool_source
    3. **预览**: 显示 LLM 生成的模板内容（代码块）
    4. **审查**: 显示安全校验结果（通过/失败及原因）
    5. **保存**: 保存成功提示 + 返回主应用链接
  - 上一步/下一步导航按钮
  - 每步数据缓存（防止回退丢失）
- [ ] 路由守卫：`/generator` 不依赖 session，独立页面
- [ ] 顶部导航栏含"返回主应用"链接

### 重构

- [ ] 确认生成器页面不干扰 MainPage 的 session 状态
- [ ] 确认保存成功后可选"立即使用此模板"跳转回主应用

**涉及文件**: `frontend/src/pages/GeneratorPage.tsx`

---

## T-UX-15: pyproject.toml 依赖更新

**设计依据**: plan-ux §9 (DC-UX-01)

### 红 — 编写测试

- [ ] `pip install -e ".[dev]"` 成功安装所有依赖
- [ ] `python -c "import fastapi; import uvicorn; import websockets"` 成功

### 绿 — 实现代码

- [ ] `SourceCode/pyproject.toml`:
  - `[project.optional-dependencies]` 或 `[dependency-groups]` 中新增 `dev` 组：
    - `fastapi >= 0.110.0`
    - `uvicorn[standard] >= 0.29.0`
    - `websockets >= 12.0`
    - `python-multipart >= 0.0.9`
  - 生产依赖保持 `anthropic`, `jinja2` 不变（P5 合规）
  - 安装命令：`pip install -e ".[dev]"`

### 重构

- [ ] 确认 CLI 模式不加载 fastapi（`python -m cli.main` 不需要 fastapi）
- [ ] 确认 ruff/mypy 配置不因新依赖报错

**涉及文件**: `SourceCode/pyproject.toml`

---

## T-UX-16: 启动脚本与文档

**设计依据**: plan-ux §7 (DC-UX-01)

### 红 — 编写测试

- [ ] 手动验证开发启动流程：
  - 终端 1: `python -m api.main` → FastAPI 启动在 8000
  - 终端 2: `cd frontend && npm run dev` → Vite 启动在 5173
  - 浏览器访问 `http://localhost:5173` → 页面加载成功

### 绿 — 实现代码

- [ ] `SourceCode/src/api/__main__.py`:
  ```python
  import sys
  from api.main import main
  sys.exit(main())
  ```
- [ ] `SourceCode/docs/README-UI.md`: UI 模式启动说明
  - 前置条件：Python 环境 + Node.js
  - 开发模式：前后端分离启动
  - 生产模式：`npm run build` + `python -m api.main`
- [ ] `CLAUDE.md` 更新：加入 `api/` 和 `frontend/` 的说明（在后续 PR 中统一更新）

### 重构

- [ ] 确认 `python -m api` 等价于 `python -m api.main`
- [ ] 确认 `python -m cli` 仍正常工作（互不干扰）

**涉及文件**: `SourceCode/src/api/__main__.py`, `SourceCode/docs/README-UI.md`

---

## 编码顺序

### 阶段一：后端 API 骨架（T-UX-01 ~ T-UX-07）

```
T-UX-01 (FastAPI 骨架) → T-UX-02 (Session API) → T-UX-03 (Templates API)
     |
     ├──→ T-UX-04 (Chat WS) ──→ T-UX-05 (Execute WS)
     |
     ├──→ T-UX-06 (Pipeline API)
     |
     └──→ T-UX-07 (Generator API)
```

**原因**：
- T-UX-01 是所有后端路由的根基，必须先完成
- T-UX-02 是核心状态机 API，依赖 T-UX-01 的依赖注入
- T-UX-03/04/05/06/07 互相独立，可并行
- WebSocket (T-UX-04/05) 依赖 T-UX-01 的 app 实例

### 阶段二：前端项目初始化（T-UX-08）

**原因**：前端所有组件依赖项目 scaffold，必须先完成。

### 阶段三：前端核心（T-UX-09 ~ T-UX-12）

```
T-UX-08 (项目初始化) → T-UX-09 (类型 + API Client) → T-UX-10 (布局 + 状态管理)
     |
     ├──→ T-UX-11 (聊天 + WS)
     |
     └──→ T-UX-12 (模板卡片 + 参数表单)
```

**原因**：
- T-UX-09 提供类型和 API 调用基础，所有前端组件依赖它
- T-UX-10 提供布局和全局状态，聊天和表单组件依赖它
- T-UX-11 和 T-UX-12 可并行

### 阶段四：前端扩展（T-UX-13 ~ T-UX-14）

```
T-UX-12 (参数表单) ──→ T-UX-13 (Pipeline 组件)
T-UX-09 (API Client) ──→ T-UX-14 (生成器页面)
```

**原因**：Pipeline 复用 ParamForm 组件；生成器页面独立。

### 阶段五：工程化（T-UX-15 ~ T-UX-16）

T-UX-15 和 T-UX-16 可并行，在所有代码完成后进行。

---

## 质量门禁（每步完成后执行）

**后端代码**：
- [ ] `ruff format src/ tests/`
- [ ] `ruff check src/ tests/`
- [ ] `mypy --strict src/`
- [ ] `pytest tests/unit/ -v`
- [ ] 覆盖率 ≥ 80%

**前端代码**：
- [ ] `cd frontend && npm run lint`（配置 ESLint）
- [ ] `cd frontend && npx tsc --noEmit`
- [ ] `cd frontend && npm run build`（零报错）

**端到端验证**：
- [ ] 后端启动成功：`python -m api.main`
- [ ] 前端启动成功：`cd frontend && npm run dev`
- [ ] 浏览器访问 `http://localhost:5173` 能加载页面
- [ ] 发送消息能收到响应

---

## 需求追溯表

| 需求 ID | 设计决策 | 任务 | 说明 |
|:-------:|:--------:|:----:|------|
| F5 | DC-UX-02 | T-UX-02, T-UX-12 | 脚本预览 + UI 按钮确认（替代 Y/N） |
| F8 | DC-UX-03 | T-UX-02, T-UX-10 | Session 快照驱动 UI，多轮上下文保留 |
| F9 | DC-UX-06 | T-UX-06, T-UX-13 | Pipeline 多任务串行 |
| P2 | DC-UX-02 | T-UX-12 | 先展后行（ScriptPreview 组件） |
| P3 | DC-UX-03 | T-UX-02 | Workspace 通过 API 初始化 |
| P5 | DC-UX-01 | T-UX-15 | fastapi 等作为 dev 依赖 |
| UX-1 | DC-UX-02 | T-UX-03, T-UX-12 | 模板卡片浏览 + 参数表单填写 |
| UX-2 | DC-UX-06 | T-UX-06, T-UX-13 | Pipeline 可视化编辑 |
| UX-3 | DC-UX-07 | T-UX-07, T-UX-14 | J2 模板生成器 UX |
| CODE-3 | DC-UX-04 | T-UX-04 | LLM 调用封装在 llm/ |
| DEP-5 | DC-UX-01 | T-UX-01 | API 层依赖规则 |
| DEP-6 | DC-UX-01 | T-UX-08 | frontend 仅通过 HTTP/WS 通信 |
| DEP-7 | DC-UX-01 | 全部 | CLI 与 API 并行不互扰 |

---

## 预估工作量

| 任务 | 复杂度 | 说明 |
|------|:------:|------|
| T-UX-01 | 中 | FastAPI 骨架 + 依赖注入设计 |
| T-UX-02 | **高** | Session 状态机 API 是核心，测试场景多 |
| T-UX-03 | 低 | 模板查询，主要是数据转换 |
| T-UX-04 | 中 | WebSocket 流式推送，需处理异步边界 |
| T-UX-05 | 中 | Execute WS，subprocess + 异步事件循环 |
| T-UX-06 | 中 | Pipeline 合并逻辑，参数关联 |
| T-UX-07 | 低 | 复用已有 generate 模块逻辑 |
| T-UX-08 | 低 | Vite scaffold，标准流程 |
| T-UX-09 | 低 | TypeScript 类型 + axios 封装 |
| T-UX-10 | 中 | Zustand store + 布局组件 |
| T-UX-11 | **高** | 聊天区域是核心交互，消息类型多 |
| T-UX-12 | **高** | 参数表单动态渲染 + 脚本预览交互 |
| T-UX-13 | 中 | Pipeline 可视化，组件嵌套 |
| T-UX-14 | 中 | 生成器 5 步向导页面 |
| T-UX-15 | 低 | pyproject.toml 编辑 |
| T-UX-16 | 低 | 启动脚本 + 文档 |
