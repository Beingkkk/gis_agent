# GIS Agent 浏览器 UI 模式

GIS Agent 浏览器 UI 是基于 React + FastAPI 的图形交互界面，与 CLI 模式共享 core/llm/templates 业务逻辑。

## 前置条件

- Python 3.10+（已安装 `anthropic`, `jinja2`, `fastapi`, `uvicorn`）
- Node.js 18+（用于前端构建）

## 开发模式（前后端分离）

### 1. 启动后端

**Windows:**
```cmd
cd SourceCode
python start_api.py
```

**Linux/macOS:**
```bash
cd SourceCode
PYTHONPATH=src python -m api.main
```

后端启动在 `http://localhost:8000`，提供：
- REST API: `/api/*`
- WebSocket: `/ws/*`
- 健康检查: `GET /health`

### 2. 启动前端

```cmd
cd SourceCode\frontend
npm install   :: 首次运行
npm run dev
```

前端开发服务器启动在 `http://localhost:5173`，通过 Vite proxy 将 `/api` 和 `/ws` 请求转发到后端。

### 3. 访问

打开浏览器访问 `http://localhost:5173`

## 生产模式

```cmd
cd SourceCode\frontend
npm run build   :: 输出到 frontend/dist/

cd ..
python start_api.py
```

生产模式下 FastAPI 自动挂载 `frontend/dist/` 为静态文件，访问 `http://localhost:8000` 即可。

## 页面路由

| 路径 | 说明 |
|------|------|
| `/` | 主应用：三栏布局（模板卡片 + 聊天 + 详情/参数） |
| `/generator` | J2 模板生成器：5 步向导（文档输入 → 配置 → 预览 → 审查 → 保存） |
| `/pipeline` | Pipeline 编排：多步骤模板串行 + 脚本合并 |

## 状态机映射

前端 UI 直接映射后端 `SessionState`：

| 状态 | UI 表现 |
|------|---------|
| `IDLE` | 探索态，浏览模板卡片，自由聊天 |
| `INTENT_CONFIRM` | 显示候选卡片，用户点击确认 |
| `PARAM_COLLECT` | 右栏展开参数表单 |
| `SCRIPT_PREVIEW` | 聊天区显示脚本 + 执行/修改/取消按钮 |
| `EXECUTING` | 实时输出执行日志 |
| `ERROR_RECOVERY` | 显示诊断结果和修复选项 |

## 端口配置

默认后端端口为 `8000`。如果冲突，修改以下两处：

**1. 后端配置**（`SourceCode/config/config.json`）：
```json
{
  "api": {
    "host": "0.0.0.0",
    "port": 9000
  }
}
```

或通过环境变量（无需改文件）：
```cmd
set GISAGENT_API_PORT=9000
python start_api.py
```

**2. 前端配置**（`SourceCode/frontend/.env`，复制自 `.env.template`）：
```
VITE_API_PORT=9000
```

前端 `.env` 控制 Vite dev server 的 proxy 目标端口，仅在开发模式生效。生产模式下前端直接调用相对路径 `/api`，由部署环境决定目标。
