# GIS Agent

基于自然语言的 GDAL 数据处理助手。接受中文需求描述，生成安全可审查的批处理脚本，经确认后执行。

**Electron 桌面应用**为唯一活跃交互入口。CLI 代码已删除（参见 [constitution.md §6.1](Document/constitution.md)）。

## 核心能力

| 能力 | 说明 |
|------|------|
| 任务脚本化 | 自然语言需求 → 两阶段意图匹配 → Jinja2 模板渲染 → 可执行脚本 |
| 模板知识 | 模板内置 `@concept`/`@note`/`@common_error` 元数据，辅助使用和错误诊断 |
| 安全执行 | 路径规范化、执行前强制确认、脚本安全扫描、临时脚本写入 `./cache/` |
| Pipeline 多步 | 多模板步骤串行编排，步骤间参数自动关联，合并为单脚本执行 |
| 模板生成器 | 从 GDAL HTML 文档自动生成 `.j2` 模板（LLM 驱动生成 → Monaco 编辑 → 安全校验 → 保存） |
| 批量转换 | 单文件脚本一键转换为遍历目录的批量脚本（WebSocket 流式） |
| 执行环境配置 | Shell/Conda 自动检测与验证，支持 bash/cmd/PowerShell，配置持久化 |

## 环境准备

### 1. 创建 Conda 环境

```bash
conda create -n gis-agent python=3.11 -y
conda activate gis-agent
```

### 2. 安装 GDAL

```bash
conda install -c conda-forge gdal -y
```

验证安装：

```bash
ogr2ogr --version
```

### 3. 安装 Node.js（Electron 桌面应用需要）

Electron 桌面应用需要 Node.js 18+：

```bash
# 进入前端目录
cd SourceCode/frontend

# 安装前端依赖（首次运行）
npm install
```

### 4. 安装 Python 依赖

```bash
# 进入源码目录
cd SourceCode

# 安装生产依赖
pip install -e .

# 如需开发（包含测试和代码检查工具，以及 FastAPI 后端依赖）
pip install -e ".[dev]"
```

### 5. 配置

复制配置模板并填入实际凭证：

```bash
cd SourceCode
cp config/config.json.template config/config.json
```

编辑 `config/config.json`（在 `SourceCode/` 目录下）：

| 字段 | 说明 | 示例 |
|------|------|------|
| `llm.base_url` | LLM API 地址 | `https://api.anthropic.com` |
| `llm.auth_key` | API 密钥 | `sk-xxxxxxxx` |
| `llm.model_name` | 模型名称 | `claude-sonnet-4-6` |
| `workspace.default_path` | 默认工作空间 | `.` |
| `api.host` | API 服务绑定地址 | `0.0.0.0` |
| `api.port` | API 服务端口 | `18000` |

**环境变量覆盖**：敏感字段和常用配置支持通过环境变量覆盖，避免密钥入仓。

```bash
# LLM 配置
export GISAGENT_LLM_AUTH_KEY="sk-your-key"
export GISAGENT_LLM_BASE_URL="https://api.example.com"

# API 端口（开发时若 18000 被占用）
export GISAGENT_API_PORT=19000

# 前端代理目标端口（开发时与 API 端口保持一致）
export VITE_API_PORT=19000
```

变量命名规则：`GISAGENT_` + 配置路径（大写，`_` 连接），优先级高于配置文件。

**Electron 模式**：Electron 启动 Python 后端时会自动注入 `ELECTRON_MODE=1`，后端据此放宽 CORS 限制以允许 `file://` 协议访问。无需手动设置。

## 启动

### Electron 桌面应用（唯一活跃入口）

基于 Electron + React + FastAPI 的桌面应用。Python 后端作为子进程由 Electron 自动管理，前端通过 IPC 调用原生文件对话框，支持返回绝对路径。

**开发模式**（热重载 + DevTools）：

```bash
cd SourceCode/frontend
npm run electron:dev
```

`concurrently` 会同时启动 Vite dev server 和 Electron；Electron 自动等待 Vite 就绪后加载窗口。

**生产构建**：

```bash
cd SourceCode/frontend
npm run electron:build
```

> **端口配置**：后端端口硬编码为 `18000`，由 Electron 主进程与 Python 子进程约定，无需用户配置。

### ~~命令行入口~~ 【已删除】

CLI 代码已于 2026-06-03 删除。所有交互通过 Electron 桌面应用进行。

参见 [constitution.md §6.1](Document/constitution.md)。

## 三 TAB 架构

Electron 桌面应用采用三 TAB 分离设计，代码层面决定场景，LLM 不猜意图：

| TAB | 职责 | 后端 API | 协议 |
|-----|------|---------|------|
| **模板识别** | 搜索模板、LLM 意图匹配、参数填写 | `POST /session/{id}/intent` | HTTP |
| **GIS 问答** | GIS 概念问答、参数用法咨询 | `WS /ws/chat/{id}` | WebSocket 流式 |
| **脚本执行** | 命令预览、执行、结果查看、错误诊断 | `WS /ws/execute/{id}` | WebSocket 实时日志 |

**Q&A 历史隔离**：`Session` 维护两个独立消息列表 — `history`（Discovery/Exec 流程消息）和 `qa_history`（Q&A 多轮对话）。WebSocket Q&A handler 读取 `qa_history` 作为对话上下文，完成后写回，确保 Q&A 历史与任务流程隔离。

### 会话状态机

| 状态 | UI 表现 | 说明 |
|------|---------|------|
| `IDLE` | 模板识别 TAB 就绪 | 浏览模板卡片，自由输入 |
| `INTENT_CONFIRM` | 显示候选模板列表 | 低置信度匹配时让用户选择 |
| `PARAM_COLLECT` | 右栏展开参数表单 | 分组折叠 + 水平行布局 |
| `SCRIPT_PREVIEW` | 脚本执行 TAB：命令预览 | 可刷新、导出脚本、执行 |
| `EXECUTING` | 脚本执行 TAB：执行中 | 实时日志推送 |
| `ERROR_RECOVERY` | 脚本执行 TAB：失败态 | **自动诊断**（无按钮），诊断结果 inline 展示 |

**错误恢复**：执行失败后系统自动触发 LLM 诊断，结果（根因 + 建议 + `can_auto_fix` + 【修复命令参考】代码块）直接展示在脚本执行 TAB 的诊断面板中，与错误输出同屏呈现。操作按钮为"修改参数"/"放弃任务"。

### 执行环境配置

脚本执行环境可在 ExecTab 中动态配置：

| 配置项 | 说明 |
|--------|------|
| Shell 类型 | bash / cmd / PowerShell，自动检测 |
| Conda 环境 | 可选，自动推导环境变量 |
| 临时脚本目录 | `./cache/`（项目相对路径，自动创建）|

用户可通过"导出脚本"按钮将当前脚本保存到任意路径（`.bat`/`.sh`/`.ps1` 根据 shell 类型自动选择后缀）。

## 项目结构

```
gis-agent/
├── Document/               # 设计文档（spec/constitution/plan/ADR）
│   ├── design/            # 架构图 + 场景-需求映射（HTML）
│   ├── archive/           # 废弃的设计文档
│   └── reports/           # 审计报告
├── SourceCode/
│   ├── src/
│   │   ├── api/           # API 层：FastAPI + WebSocket 适配（Electron 后端）
│   │   ├── core/          # 核心层：状态机、模板注册表、参数校验、匹配引擎
│   │   ├── llm/           # LLM 层：意图分类、参数抽取、问答、错误诊断、模板生成
│   │   ├── templates/     # 模板引擎：Jinja2 渲染、扫描器、安全校验
│   │   ├── config/        # 配置加载与校验
│   │   └── rag/           # RAG 预处理（开发时工具，不运行时加载）
│   ├── frontend/          # 前端（React + TypeScript + Vite + Electron）
│   │   ├── electron/      # Electron 主进程与预加载脚本
│   │   │   ├── main.ts    # 主进程：无边框窗口 + Python 子进程 + IPC
│   │   │   ├── preload.ts # 预加载脚本：contextBridge 暴露 API
│   │   │   └── tsconfig.json
│   │   ├── src/
│   │   │   ├── api/       # HTTP/WebSocket 客户端封装
│   │   │   ├── components/# React 组件（三 TAB + 参数表单 + 执行面板）
│   │   │   ├── hooks/     # Zustand 状态管理 + WebSocket
│   │   │   ├── pages/     # 页面路由（/ 主应用 /generator /pipeline）
│   │   │   ├── electron-api.ts  # IPC API 封装（文件对话框、窗口控制）
│   │   │   └── types/     # TypeScript 类型定义
│   │   ├── package.json
│   │   └── vite.config.ts
│   ├── tests/unit/        # 单元测试
│   ├── tests/integration/ # 集成测试（含共享 fixture）
│   ├── scripts/           # 开发辅助脚本（J2 批量生成、E2E 测试等）
│   ├── data/
│   │   └── templates/     # .j2 模板文件（vector/raster/general）
│   ├── cache/             # 脚本执行临时文件目录（自动创建）
│   ├── config/            # 运行时配置（config.json，gitignored）
│   ├── start_api.py       # API 服务启动脚本（由 Electron 内部调用）
│   └── pyproject.toml
└── README.md
```

## 开发工具

### 批量生成 J2 模板

`scripts/generate_templates.py` 是一个开发时工具，用于从 GDAL HTML 文档批量生成 Jinja2 模板。当你需要扩充模板库（如 GDAL 版本升级、新增工具支持）时，使用此工具替代手工编写。

**工作原理**：HTML 解析 → LLM 生成模板定义 → LLM 审核 → 渲染为 `.j2` 文件。

**前置条件**：
- 已配置有效的 LLM API 密钥（`config/config.json`）
- 已构建 GDAL 文档（`Document/Resource/gdal/build/doc/build/html/programs`）

**执行命令**：

```bash
cd SourceCode

# 批量生成（从 programs 目录生成到 data/templates/）
python scripts/generate_templates.py \
  --source ../Document/Resource/gdal/build/doc/build/html/programs \
  --output data/templates/ \
  --config config/config.json
```

**参数说明**：

| 参数 | 说明 |
|------|------|
| `--source` | GDAL HTML 文档目录 |
| `--output` | J2 模板输出目录 |
| `--config` | 配置文件路径 |
| `--strict` | 严格审核模式（任何 warning 视为失败） |
| `--dry-run` | 空跑预览（不写入文件，但仍有 API 调用） |
| `--force` | 强制重跑（忽略断点续传缓存） |
| `--verbose` | 详细日志 |

**断点续传**：工具会自动跳过已处理的文件（通过 `.generate_state.json` 跟踪）。中断后重新执行同一命令即可恢复。

**审核队列**：生成或审核失败的文件会记录到 `.review_queue.jsonl`，可据此人工修正后补充模板。

**注意事项**：
- 该工具不是运行时组件，仅在开发时执行
- 批量处理涉及大量 LLM API 调用，请注意 token 消耗
- 生成的模板建议人工抽样检查后再提交

## 开发规范

本项目遵循规范驱动设计（Specification-Driven Design）流程。编码前必须先完成对应模块的 plan 设计文档，详见 [Document/constitution.md](Document/constitution.md)。

