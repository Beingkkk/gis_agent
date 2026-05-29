# plan-ux

| 项目 | 内容 |
|------|------|
| 版本 | v1.0.0 |
| 状态 | 草案 |
| 作者 | - |
| 日期 | 2026-05-29 |

---

## 1. 设计概述

### 1.1 模块职责

实现 GIS Agent 的图形用户界面：基于浏览器的前端交互层，通过 HTTP API 和 WebSocket 与后端通信。本模块**替换原有的 CLI 层（`cli/`）**，复用 core、llm、templates 三层业务逻辑，将 REPL 文本交互升级为可视化卡片、表单、对话流的交互范式。

本模块同时覆盖 Pipeline 多任务串行和 J2 模板生成器两个新增功能的 UX。

### 1.2 所属架构层次

前端层（`frontend/`）+ API 层（`api/`）。

- `frontend/` 为纯前端代码（React + TypeScript），通过 HTTP/WebSocket 调用后端
- `api/` 为后端适配层（FastAPI），将现有 core/llm/templates 能力暴露为 REST + WS 接口
- `core/`、`llm/`、`templates/` 完全复用，**不做任何修改**

### 1.3 对应需求项

| 需求 ID | 需求描述 |
|:-------:|---------|
| F5 | 向用户完整展示脚本内容，要求明确确认后执行（UI 按钮替代 Y/N） |
| F8 | 会话内记忆（多轮追问和补充） |
| P2 | 先展后行：脚本预览 + 确认执行 |
| UX-1 | 模板以卡片形式浏览，参数以表单形式填写 |
| UX-2 | Pipeline 多任务串行的可视化编辑和合并脚本生成 |
| UX-3 | J2 模板生成器：文档输入 → LLM 生成 → 审查 → 保存 |

---

## 2. 设计决策

### DC-UX-01: 采用浏览器方案（React + FastAPI），不打包 Electron

**决策**: 前端使用 React + TypeScript + Vite 构建，后端使用 FastAPI 提供 HTTP API 和 WebSocket。用户启动后端服务后，自动打开浏览器标签访问本地地址。

**理由**:
- 避免 Electron 打包复杂性和包体积问题
- 前端代码与桌面方案 100% 兼容，未来可随时升级为 Electron
- FastAPI 原生支持 WebSocket，LLM 流式和脚本执行日志的实时推送实现简单
- 开发与 CLI 版本并行运行，互不干扰

### DC-UX-02: CLI 状态机直接映射为 UI 状态，不改核心逻辑

**决策**: `core/models.py` 中的 `SessionState` 6 状态 Enum 保持不变。UI 层通过 `Session.state` 值判断当前应渲染的界面元素。

**理由**:
- 状态机是核心资产，其正确性已在 CLI 中验证
- UI 只是状态机的另一种呈现方式，状态流转规则完全一致
- 避免为 UI 引入第二套状态管理，防止状态不一致

**映射关系**:

| SessionState | UI 表现 | 用户操作 |
|-------------|---------|---------|
| `IDLE` | 探索态 | 左栏浏览卡片，聊天自由问答 |
| `INTENT_CONFIRM` | 意图确认 | 聊天区显示候选卡片，用户点击"确认"按钮 |
| `PARAM_COLLECT` | 参数填写 | 右栏展开表单，用户直接输入 |
| `SCRIPT_PREVIEW` | 脚本预览 | 聊天区显示脚本代码块 + 执行/修改/取消按钮 |
| `EXECUTING` | 执行中 | 脚本区变为进度状态，实时输出日志 |
| `ERROR_RECOVERY` | 错误恢复 | 聊天区显示诊断结果 + 修复选项 |

### DC-UX-03: Session 对象由后端维护，前端仅持有 session_id

**决策**: 前端不维护完整的 `Session` 对象，每次交互携带 `session_id`，后端返回更新后的 `Session` 快照。前端根据快照更新 UI。

**理由**:
- `Session` 是核心层复杂数据结构，前端不需要了解其内部结构
- 前端只需消费 `Session` 中用于展示的字段（state、task_context、params、history）
- 防止前后端状态漂移

**接口示例**:
```typescript
// 前端持有的最小状态
interface UIState {
  sessionId: string;
  state: 'IDLE' | 'INTENT_CONFIRM' | 'PARAM_COLLECT' | 'SCRIPT_PREVIEW' | 'EXECUTING' | 'ERROR_RECOVERY';
  taskContext: TaskContext | null;
  messages: ChatMessage[];
  lockedTemplateId: string | null;
}
```

### DC-UX-04: LLM 流式输出通过 WebSocket 推送

**决策**: Q&A 对话和脚本生成等需要流式输出的场景，使用 WebSocket 连接，后端将 LLM 的 `on_chunk` 回调内容逐片推送到前端。

**理由**:
- `llm/chat_stream()` 和 `llm/answer_question()` 已通过 `on_chunk` 回调支持流式（DC-0068/DC-0069）
- 后端只需将 callback 接入 WebSocket send，无需改动 LLM 层
- SSE 在重新连接时容易丢失中间状态，WebSocket 更适合持续会话

### DC-UX-05: 脚本执行日志通过 WebSocket 实时推送

**决策**: 脚本执行不再使用 `subprocess.run()` 的阻塞模式，改用 `subprocess.Popen()` 逐行读取 stdout/stderr，通过独立 WebSocket 连接推送到前端。

**理由**:
- UI 需要实时展示执行进度（如 `0...10...20...`），阻塞模式无法提供增量输出
- 与 CLI 的 `--dry-run` 模式兼容：dry-run 时只返回脚本预览，不启动 subprocess
- 超时控制保持 300 秒，超时后主动断开 WS 并提示

### DC-UX-06: Pipeline 多任务在 core 层外独立管理

**决策**: Pipeline（多任务串行）不改动 `Session` 状态机，而是在前端维护一个 `Pipeline` 对象，提交执行时由后端合并为单脚本。

**理由**:
- `Session` 状态机设计为单任务生命周期，引入 Pipeline 会显著增加复杂度
- Pipeline 本质是多张模板的参数组合 + 步骤间自动关联，前端天然适合管理这种列表结构
- 执行时后端将 Pipeline 展开为多步骤脚本，复用现有 `ScriptExecutor`

**Pipeline 结构**:
```typescript
interface Pipeline {
  id: string;
  steps: PipelineStep[];        // 有序步骤列表
  autoLinks: DataLink[];        // 步骤间自动关联规则
}

interface PipelineStep {
  order: number;
  templateId: string;
  params: Record<string, string>;
}

interface DataLink {
  fromStep: number;
  fromParam: string;            // 通常是 "output"
  toStep: number;
  toParam: string;
}
```

### DC-UX-07: 模板生成器作为独立子页面

**决策**: J2 模板生成器（LLM 驱动的文档→模板）不集成在主应用状态机中，而是作为独立路由 `/generator`，完成后返回主应用。

**理由**:
- 模板生成是开发工具，使用频率远低于主任务流程
- 独立页面避免干扰主应用的状态管理
- 生成器有自己的 5 步向导（文档输入 → 配置 → 预览 → 审查 → 保存），不适合塞进主状态机

---

## 3. 接口定义

### 3.1 REST API

```python
# api/routes/session.py

@router.post("/session", response_model=SessionResponse)
async def create_session(workspace: Optional[str] = None) -> Session:
    """创建新会话，返回 session_id 和初始状态。"""

@router.post("/session/{session_id}/intent", response_model=SessionResponse)
async def process_intent(session_id: str, request: IntentRequest) -> Session:
    """用户输入自然语言需求，返回匹配模板和候选列表。"""

@router.post("/session/{session_id}/lock", response_model=SessionResponse)
async def lock_template(session_id: str, request: LockRequest) -> Session:
    """用户确认模板，进入 PARAM_COLLECT 状态。"""

@router.post("/session/{session_id}/params", response_model=SessionResponse)
async def submit_params(session_id: str, request: ParamsRequest) -> Session:
    """提交参数，返回渲染后的脚本预览（SCRIPT_PREVIEW）。"""

@router.post("/session/{session_id}/execute", response_model=ExecutionResponse)
async def execute_script(session_id: str, dry_run: bool = False) -> ExecutionResponse:
    """确认执行脚本。实际执行走 WebSocket，此接口仅触发。"""

@router.post("/session/{session_id}/clear")
async def clear_session(session_id: str):
    """清空会话，重置为 IDLE。"""

@router.post("/session/{session_id}/workspace", response_model=SessionResponse)
async def update_session_workspace(session_id: str, request: WorkspaceRequest) -> Session:
    """更新工作空间路径，验证目录存在后切换，并清空当前会话。"""

# api/routes/templates.py

@router.get("/templates", response_model=List[TemplateDef])
async def list_templates() -> List[TemplateDef]:
    """返回所有扫描到的模板列表（复用 TemplateRegistry）。"""

@router.get("/templates/{template_id}", response_model=TemplateDetail)
async def get_template(template_id: str) -> TemplateDetail:
    """返回模板详情（参数定义、概念、注意事项、错误说明）。"""

# api/routes/pipeline.py

@router.post("/pipeline", response_model=ScriptPreview)
async def preview_pipeline(request: PipelineRequest) -> ScriptPreview:
    """提交 Pipeline，返回合并后的多步骤脚本预览。"""

@router.post("/pipeline/execute")
async def execute_pipeline(request: PipelineRequest) -> ExecutionResponse:
    """执行 Pipeline 合并脚本。"""

# api/routes/generator.py (模板生成器)

@router.post("/generator/generate", response_model=GeneratedTemplate)
async def generate_template(request: GenerateRequest) -> GeneratedTemplate:
    """提交文档和配置，LLM 生成 J2 模板。"""

@router.post("/generator/validate")
async def validate_template(request: ValidateRequest) -> ValidationResult:
    """对生成的模板进行安全扫描和语法校验。"""

@router.post("/generator/save")
async def save_template(request: SaveRequest):
    """保存审查通过的模板到 data/templates/ 目录。"""
```

### 3.2 WebSocket 接口

```python
# api/websocket.py

class ChatWebSocket:
    """Q&A 流式对话。前端发送消息，后端通过 LLM 流式推送回复。"""
    
    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        # 复用 llm/answer_question() 的 on_chunk 回调
        # 每收到一个 chunk，websocket.send_text(chunk)

class ExecuteWebSocket:
    """脚本执行实时日志。前端连接后，后端启动 subprocess 并逐行推送输出。"""
    
    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        # 使用 subprocess.Popen 而非 run
        # 逐行读取 stdout/stderr，websocket.send_text(line)
        # 完成后发送 {"type": "done", "success": true, "output_path": "..."}
```

### 3.3 核心数据结构（前后端共享）

```typescript
// 前端从后端 Session 快照中提取的展示结构

interface SessionSnapshot {
  session_id: string;
  state: SessionState;
  task_context: {
    template_id: string | null;
    template_name: string | null;
    params: Record<string, string>;
    missing_params: string[];
    candidates: CandidateTemplate[];
  };
  script_preview: string | null;
  error_context: ErrorContext | null;
  history: ChatMessage[];
  workspace: string;
}

interface ChatMessage {
  role: 'user' | 'agent';
  content: string;
  type?: 'text' | 'cards' | 'script' | 'timeline' | 'error';
  meta?: Record<string, any>;   // 卡片列表、脚本内容、时间线数据等
}

interface TemplateDef {
  id: string;
  name: string;
  description: string;
  category: 'vector' | 'raster' | 'general' | 'database';
  tool_source: string;           // GDAL, GRASS, SAGA, PostGIS, etc.
  tags: string[];
}

interface TemplateDetail extends TemplateDef {
  params: ParamDef[];
  concepts: ConceptItem[];
  notes: string[];
  common_errors: CommonErrorItem[];
  seealso: string[];
}
```

---

## 4. 状态机与数据流

### 4.1 单任务流程

```
用户打开浏览器 ──→ GET /templates（加载左栏卡片）
                      │
                      ▼
用户输入需求 ──→ POST /session/{id}/intent
                      │
              ┌──────┼──────┐
              │      │      │
              ▼      ▼      ▼
       精确匹配  探索性问题  部分/无匹配
              │      │      │
              ▼      ▼      ▼
        PARAM_COLLECT  IDLE   INTENT_CONFIRM
   （直达参数填写）  (Q&A   （top-N 候选卡片
               │     文本回复)   供用户确认）
               │      │      │
               │      │      └─→ 用户点击确认
               │      │           POST /session/{id}/lock
               │      │                │
               └──────┴────────────────┘
                                    │
                                    ▼
                        进入 PARAM_COLLECT（右栏表单展开）
                                    │
                        用户填写参数 ──→ POST /session/{id}/params
                                    │
                                    ▼
                        返回脚本预览（SCRIPT_PREVIEW）
                                    │
                        用户点击执行 ──→ WS /ws/execute 连接
                                    │
                                    ▼
                        实时推送执行日志（EXECUTING → IDLE）
```

### 4.2 Pipeline 流程

```
用户描述多步骤需求
       │
       ▼
后端解析为 Pipeline 结构（多个模板 + 关联规则）
       │
       ▼
前端进入 Pipeline 模式：
   - 聊天区显示横向时间线概览
   - 右栏纵向堆叠任务卡片
   - 步骤间显示数据流指示条
       │
用户检查/修改每步参数
       │
       ▼
点击"生成脚本" ──→ POST /pipeline（返回合并脚本预览）
       │
       ▼
用户确认执行 ──→ POST /pipeline/execute（走 WS 实时日志）
```

---

## 5. 前端组件结构

```
frontend/
├── src/
│   ├── main.tsx                    # 入口，启动时请求 /session 创建会话
│   ├── App.tsx                     # 路由：/ /generator /pipeline
│   ├── api/
│   │   ├── client.ts               # axios 实例，baseURL = "/api"
│   │   ├── session.ts              # 会话相关 API 调用
│   │   ├── templates.ts            # 模板相关 API 调用
│   │   ├── pipeline.ts             # Pipeline API
│   │   └── generator.ts            # 模板生成器 API
│   ├── components/
│   │   ├── Layout.tsx              # 三栏布局框架
│   │   ├── TopBar.tsx              # 顶部栏（Logo + 状态 + 工作区信息）
│   │   ├── TemplateCardList.tsx    # 左栏：模板卡片列表
│   │   ├── ChatArea.tsx            # 中栏：聊天消息 + 输入框
│   │   ├── ChatMessage.tsx         # 单条消息气泡（支持多种 type）
│   │   ├── DetailPanel.tsx         # 右栏：模板详情 / 参数表单
│   │   ├── ParamForm.tsx           # 参数表单组件
│   │   ├── ScriptPreview.tsx       # 脚本代码块预览
│   │   ├── PipelineOverview.tsx    # Pipeline 横向时间线
│   │   ├── PipelineStepCard.tsx    # Pipeline 纵向任务卡片
│   │   └── DataFlowIndicator.tsx   # 步骤间数据流指示
│   ├── hooks/
│   │   ├── useSession.ts           # 会话状态管理（Zustand）
│   │   ├── useWebSocket.ts         # WebSocket 连接管理
│   │   └── useTemplates.ts         # 模板列表和详情
│   ├── pages/
│   │   ├── MainPage.tsx            # 主应用页面
│   │   ├── GeneratorPage.tsx       # 模板生成器页面
│   │   └── PipelinePage.tsx        # Pipeline 编排页面
│   └── types/
│       └── index.ts                # TypeScript 类型定义
├── index.html
├── vite.config.ts
└── .env.template                   # 前端环境变量模板（API 端口）
```

---

## 6. 后端文件结构（新增）

```
SourceCode/src/
├── api/                            # 新增：HTTP + WebSocket 适配层
│   ├── __init__.py
│   ├── main.py                     # FastAPI app 实例，CORS，路由注册
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── session.py              # 会话状态流转 API
│   │   ├── templates.py            # 模板查询 API
│   │   ├── pipeline.py             # Pipeline 合并脚本 API
│   │   └── generator.py            # J2 模板生成器 API
│   ├── websocket/
│   │   ├── __init__.py
│   │   ├── chat.py                 # Q&A 流式 WS
│   │   └── execute.py              # 执行日志流式 WS
│   └── dependencies.py             # FastAPI Depends：Session 获取、Workspace 初始化
├── core/                           # 完全复用，不修改
├── llm/                            # 完全复用，不修改
├── templates/                      # 完全复用，不修改
└── ...
```

---

## 7. 启动方式

```bash
cd SourceCode

# 方式 1：开发模式（前后端分离启动）
# 终端 1
python start_api.py

# 终端 2
cd frontend && npm run dev

# 方式 2：生产模式（后端托管前端静态文件）
# 前端 build 后，FastAPI 挂载 static 目录
python start_api.py
# 访问 http://localhost:8000
```

### 端口配置

后端端口通过 `config/config.json` 的 `api.port` 配置，默认 8000：
```json
{
  "api": { "host": "0.0.0.0", "port": 9000 }
}
```

前端开发服务器通过 `frontend/.env` 同步代理目标：
```
VITE_API_PORT=9000
```

---

## 8. 与 CLI 的兼容性

UX 方案**不删除**现有 CLI 代码。`cli/` 目录保持完整，与 `api/` 并行存在：

- `python start_cli.py` → 启动命令行版本
- `python start_api.py` → 启动浏览器版本

两套入口共享 core/llm/templates，互不干扰。CLI 的维护成本不增加。

---

## 9. 依赖增量（相对现有）

**后端新增**（放入 `pyproject.toml` 的 `dev` 组，不影响 CLI 依赖）：
- `fastapi` — Web 框架
- `uvicorn[standard]` — ASGI 服务器
- `websockets` — WebSocket 支持
- `python-multipart` — 文件上传支持

**前端新增**：
- `react`, `react-dom`, `react-router-dom`
- `typescript`, `vite`
- `zustand` — 状态管理
- `tailwindcss`, `shadcn/ui` — UI 组件
- `axios` — HTTP 客户端

**现有依赖不变**：`anthropic`, `jinja2`（P5 仍然满足）

---

## 附录：变更记录

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.0.0 | 2026-05-29 | 初版，定义 React + FastAPI 浏览器 UI 方案 |
| v1.1.0 | 2026-05-29 | 新增 `/pipeline` 路由；启动方式改为 `start_api.py`/`start_cli.py`；端口支持前后端配置同步 |
