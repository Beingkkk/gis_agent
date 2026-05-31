# plan-electron

| 项目 | 内容 |
|------|------|
| 版本 | v1.2.0 |
| 状态 | 设计基线 |
| 作者 | - |
| 日期 | 2026-05-31 |

---

## 1. 设计概述

### 1.1 模块职责

为 GIS Agent 提供桌面应用外壳，解决标准浏览器无法访问本地文件系统绝对路径的安全限制。Electron 主进程负责：

- 创建应用窗口，加载前端页面
- 提供原生文件/目录选择对话框（IPC）
- 管理 Python FastAPI 后端进程的生命周期（启动、监控、退出清理）
- 向前端暴露安全的 Node.js API 子集

前端 React 代码和 Python FastAPI 后端代码**不做架构性改动**，仅增加 Electron 适配层。

### 1.2 所属架构层次

前端层（`frontend/`）的扩展，新增 `frontend/electron/` 子目录。Electron 主进程与 Python 后端为**同进程级兄弟关系**（Electron 主进程启动 Python 子进程）。

### 1.3 对应需求项

| 需求 ID | 需求描述 |
|:-------:|---------|
| F6 | 用户指定工作空间（本地目录） |
| F7 | 参数中文件/目录路径的选择与校验 |
| UX-1 | 模板参数表单支持文件路径浏览 |
| P3 | 最小权限：工作空间路径规范化 |

---

## 2. 设计决策

### DC-E01: 采用 Electron 壳 + 独立 Python 后端（方案B）

**决策**: Electron 仅作为桌面外壳，Python FastAPI 作为独立子进程运行。前端通过 HTTP/WebSocket 与 Python 后端通信，文件对话框通过 IPC 调用主进程。

**架构**:

```
┌─────────────────────────────────────────┐
│         Electron 主进程 (Node.js)        │
│  ┌──────────────┐  ┌─────────────────┐  │
│  │ BrowserWindow│  │ child_process   │  │
│  │  (React UI)  │  │  spawn(python)  │  │
│  │              │  │  → FastAPI :8000│  │
│  └──────┬───────┘  └─────────────────┘  │
│         │ IPC (文件对话框)               │
│         ▼                                │
│  dialog.showOpenDialog({                 │
│    properties: ['openDirectory']         │
│  }) → 返回绝对路径                        │
└─────────────────────────────────────────┘
            │
            ▼ HTTP / WebSocket
    ┌─────────────────┐
    │  Python FastAPI │  ← 完全不动
    │  (conda env)    │
    └─────────────────┘
```

**理由**:
- **后端零改动**：FastAPI 代码、API 路由、WebSocket 处理完全复用
- **前端改动最小**：仅需把文件浏览从 `<input type="file">` 改为 IPC 调用，其余业务逻辑不变
- **conda 独立管理**：不打包进 Electron， Electron 只负责用已有 conda 环境启动 Python
- **开发体验好**：前后端仍可独立开发调试，Electron 只在最后集成

**替代方案（已否决）**:
- 方案A（全内置）：Python 内嵌到 Electron 主进程。否决理由：conda 环境打包复杂，开发调试困难，违反 DEP-4（外部库类型不泄露）
- 继续使用浏览器：标准浏览器的 `<input type="file">` 无法返回绝对路径，导致工作空间设置和参数路径浏览功能无法使用

### DC-E02: IPC 接口最小化原则

**决策**: Electron 预加载脚本只暴露 3 个 API：`selectFile`、`selectDirectory`、`getApiBaseUrl`。禁止暴露完整的 `fs`、`path`、`child_process` 等 Node.js 模块。

**接口**:

```typescript
// preload.ts 暴露的 API
interface ElectronAPI {
  selectFile(options?: {
    title?: string;
    defaultPath?: string;
    filters?: { name: string; extensions: string[] }[];
  }): Promise<string | null>;
  selectDirectory(options?: {
    title?: string;
    defaultPath?: string;
  }): Promise<string | null>;
  getApiBaseUrl(): Promise<string | null>;
}
```

**理由**:
- 最小暴露面 = 最小攻击面，符合安全原则
- `getApiBaseUrl` 使渲染进程能构造绝对 API/WebSocket URL（`file://` 协议无法使用相对路径）
- 未来如需扩展（如拖拽文件），可在预加载脚本中新增独立方法

### DC-E03: Python 后端进程由 Electron 主进程托管

**决策**: Electron 主进程在 `app.whenReady()` 后启动 Python FastAPI 子进程，在 `app.quit()` 前终止子进程。后端端口从 `config.json` 动态读取（默认 18000），而非硬编码。

**启动流程**:

```typescript
// main.ts
app.whenReady().then(async () => {
  // 1. 启动 Python 后端
  const pythonProc = await startPythonBackend();
  
  // 2. 等待后端就绪（轮询 /health 或固定延时）
  await waitForBackend('http://localhost:8000');
  
  // 3. 创建窗口
  createMainWindow();
});
```

**进程管理**:

| 事件 | 行为 |
|------|------|
| `app.whenReady()` | 启动 Python 子进程 |
| 后端进程 stdout | 重定向到 Electron 主进程控制台（开发模式） |
| 后端进程 stderr | 同上，便于调试 |
| 后端进程异常退出 | 显示错误对话框，提示用户检查 conda 环境 |
| `app.quit()` / 窗口关闭 | 发送 SIGTERM → 等待 5s → SIGKILL（强制） |
| 前端 `window.beforeunload` | 无需特殊处理，后端随主进程退出 |

**Conda 环境定位**:

Electron 主进程通过硬编码路径启动 conda 环境的 Python：

```typescript
const pythonPath = process.platform === 'win32'
  ? 'C:/Users/PC/.conda/envs/gis-agent/python.exe'
  : '/Users/PC/.conda/envs/gis-agent/bin/python';

const scriptPath = path.join(__dirname, '../../start_api.py');
```

**理由**:
- 硬编码路径在项目内一致，避免运行时查找开销
- 跨平台差异仅在路径分隔符和可执行文件名
- 未来可通过配置文件或环境变量覆盖

### DC-E04: 前端文件浏览统一走 Electron IPC

**决策**: `ParamForm` 和 `ChatArea` 中的浏览按钮统一调用 `window.electron.selectFile()` / `selectDirectory()`，返回绝对路径。前端不再支持纯浏览器模式运行。

**改造点**:

| 文件 | 原实现 | 新实现 |
|------|--------|--------|
| `ChatArea.tsx` | `<input webkitdirectory>` | `window.electron.selectDirectory()` |
| `ParamForm.tsx` | `<input type="file">` / `<input webkitdirectory>` | `window.electron.selectFile()` / `selectDirectory()` |

**封装**:

```typescript
// frontend/src/electron-api.ts
export async function selectDirectory(options?: {
  title?: string;
  defaultPath?: string;
}): Promise<string | null> {
  if (window.electron) {
    return window.electron.selectDirectory(options);
  }
  return null;
}
```

**理由**:
- 统一封装避免散布 `window.electron` 类型断言
- 浏览器安全沙箱无法返回绝对路径，故不再支持纯浏览器入口

### DC-E05: 打包策略为 Electron + 源码分发

**决策**: Electron 打包包含：Electron 运行时 + 前端构建产物 + Python 源码。不包含 Python 解释器和 conda 环境。安装程序提示用户预先安装 conda 并创建 `gis-agent` 环境。

**分发结构**:

```
GIS-Agent-Setup.exe
├── GIS Agent.app/          # Electron 应用
│   ├── electron.exe
│   ├── resources/
│   │   ├── app/            # 前端构建产物 (vite build)
│   │   └── python/         # Python 源码 (src/, data/, scripts/)
│   └── ...
└── README.txt              # "请先安装 conda 并运行 conda env create..."
```

**理由**:
- 不打包 Python + conda 可大幅减小安装包体积（从 >500MB 降到 ~100MB）
- GDAL + 地理库依赖复杂，打包容易出错
- 目标用户为 GIS 开发者，具备 conda 安装能力
- 源码分发便于用户自定义模板和配置

### DC-E06: 工作空间路径控件自适应宽度

**决策**: `TopBar` 中的工作空间路径显示区域由固定 `max-w-[200px]` 改为自适应宽度，优先显示完整路径。采用 `min-w-0 flex-1` + `truncate` 组合，让路径在可用空间内尽可能展示，超出时尾部截断并保留 `title` tooltip。

**改造点**:

| 文件 | 原实现 | 新实现 |
|------|--------|--------|
| `TopBar.tsx` | `max-w-[200px] truncate` 固定宽度 | `min-w-0 flex-1 truncate` 弹性自适应 |

**理由**:
- 路径信息是用户定位工作上下文的关键，固定宽度在宽屏下浪费空间且难以辨识
- Flex 布局下配合 `min-w-0` 可正确触发 `truncate`，同时允许伸展

### DC-E07: 无边框窗口 + 自定义标题栏

**决策**: Electron 窗口设置 `frame: false` 移除原生标题栏和边框，由前端 React 组件渲染自定义标题栏，包含应用标识、拖动区域、三个窗口控制按钮（最小化、最大化/还原、关闭）。

**架构**:

```
┌─────────────────────────────────────────────────────────────┐
│  [拖动区域] GIS Agent      ─ □ ✕   ← 自定义标题栏 (React)    │  ← 32px height
├─────────────────────────────────────────────────────────────┤
│                                                             │
│                        React UI 内容区                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**窗口创建配置**:

```typescript
// main.ts
mainWindow = new BrowserWindow({
  width: 1400,
  height: 900,
  frame: false,           // ← 移除原生标题栏
  titleBarStyle: 'hidden', // macOS 兼容
  // ...
})
```

**新增 IPC 接口**:

```typescript
// preload.ts 暴露
interface ElectronAPI {
  // ... existing APIs
  windowControl: {
    minimize(): Promise<void>;
    maximize(): Promise<void>;
    close(): Promise<void>;
    isMaximized(): Promise<boolean>;
  }
}
```

**标题栏实现要点**:
- 左侧：应用 Logo + 名称（不参与拖动时作为文本展示）
- 中部：`-webkit-app-region: drag` 拖动区域，占满剩余空间
- 右侧：窗口控制按钮（最小化 `_`、最大化/还原 `□`、关闭 `✕`）
- 按钮区域设置 `-webkit-app-region: no-drag` 确保按钮可点击
- 标题栏高度 38px，兼顾视觉舒适度与点击易用性

**交互细节**:
- **双击最大化/还原**：双击中部拖动区域触发窗口最大化或还原
- **窗口状态实时同步**：主进程监听 `BrowserWindow` 的 `maximize` / `unmaximize` / `resize` 事件，通过 `webContents.send('window:state-change', { isMaximized })` 主动推送给渲染进程，确保最大化/还原按钮图标始终与窗口实际状态一致
- **工作空间路径点击复制**：点击工作空间路径区域，将完整路径写入剪贴板并给出视觉反馈
- **按钮 hover 动画**：最小化/最大化按钮 hover 时背景色渐变，关闭按钮 hover 时变为红色并反白图标

**状态栏去除**:
- Electron 默认不显示状态栏，无需额外配置
- 前端原 `TopBar` 中状态徽章保留，作为应用内部状态指示

**理由**:
- 统一跨平台视觉体验（Windows/macOS/Linux 原生标题栏样式差异大）
- 为后续主题切换（深色/浅色）提供一致性基础
- `frame: false` 是 Electron 跨平台自定义标题栏的标准方案

---

## 3. 接口定义

### 3.1 Electron 主进程 → 渲染进程（预加载脚本）

```typescript
// frontend/electron/preload.ts
import { contextBridge, ipcRenderer } from 'electron';

export interface ElectronAPI {
  selectFile(options?: SelectFileOptions): Promise<string | null>;
  selectDirectory(options?: SelectDirectoryOptions): Promise<string | null>;
  getApiBaseUrl(): Promise<string | null>;
  windowControl: WindowControlAPI;
}

interface SelectFileOptions {
  title?: string;
  defaultPath?: string;
  filters?: { name: string; extensions: string[] }[];
}

interface SelectDirectoryOptions {
  title?: string;
  defaultPath?: string;
}

interface WindowControlAPI {
  minimize(): Promise<void>;
  maximize(): Promise<void>;
  close(): Promise<void>;
  isMaximized(): Promise<boolean>;
}

contextBridge.exposeInMainWorld('electron', {
  selectFile: async (options?: SelectFileOptions): Promise<string | null> => {
    return ipcRenderer.invoke('dialog:selectFile', options);
  },

  selectDirectory: async (options?: SelectDirectoryOptions): Promise<string | null> => {
    return ipcRenderer.invoke('dialog:selectDirectory', options);
  },

  getApiBaseUrl: async (): Promise<string | null> => {
    return ipcRenderer.invoke('app:getApiBaseUrl');
  },

  windowControl: {
    minimize: async (): Promise<void> => {
      return ipcRenderer.invoke('window:minimize');
    },
    maximize: async (): Promise<void> => {
      return ipcRenderer.invoke('window:maximize');
    },
    close: async (): Promise<void> => {
      return ipcRenderer.invoke('window:close');
    },
    isMaximized: async (): Promise<boolean> => {
      return ipcRenderer.invoke('window:isMaximized');
    },
  },
} as ElectronAPI);
```

### 3.2 Electron 主进程 IPC 处理

```typescript
// frontend/electron/main.ts (片段)
import { ipcMain, dialog } from 'electron';

ipcMain.handle('dialog:selectFile', async (_, options) => {
  const result = await dialog.showOpenDialog(mainWindow, {
    ...options,
    properties: ['openFile'],
  });
  return result.canceled ? null : result.filePaths[0];
});

ipcMain.handle('dialog:selectDirectory', async (_, options) => {
  const result = await dialog.showOpenDialog(mainWindow, {
    ...options,
    properties: ['openDirectory'],
  });
  return result.canceled ? null : result.filePaths[0];
});

ipcMain.handle('app:getApiBaseUrl', () => {
  return `http://localhost:${getBackendPort()}`;
});

// Window control handlers (DC-E07)
ipcMain.handle('window:minimize', () => {
  mainWindow?.minimize();
});

ipcMain.handle('window:maximize', () => {
  if (mainWindow?.isMaximized()) {
    mainWindow.unmaximize();
  } else {
    mainWindow?.maximize();
  }
});

ipcMain.handle('window:close', () => {
  mainWindow?.close();
});

ipcMain.handle('window:isMaximized', () => {
  return mainWindow?.isMaximized() ?? false;
});
```

### 3.3 Python 进程管理

```typescript
// frontend/electron/main.ts (片段)
interface PythonProcessManager {
  start(): Promise<ChildProcess>;
  stop(): Promise<void>;
  isRunning(): boolean;
}

function createPythonManager(): PythonProcessManager {
  let proc: ChildProcess | null = null;
  
  return {
    start(): Promise<ChildProcess> {
      return new Promise((resolve, reject) => {
        const pythonPath = getPythonPath();  // 平台相关
        const scriptPath = getScriptPath();  // start_api.py 路径
        
        proc = spawn(pythonPath, [scriptPath], {
          cwd: getProjectRoot(),
          env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
        });
        
        // 等待就绪信号（或轮询 /health）
        proc.stdout?.on('data', (data) => {
          const text = data.toString();
          if (text.includes('Uvicorn running')) {
            resolve(proc!);
          }
        });
        
        setTimeout(() => reject(new Error('Backend startup timeout')), 30000);
      });
    },
    
    stop(): Promise<void> {
      return new Promise((resolve) => {
        if (!proc || proc.killed) {
          resolve();
          return;
        }
        proc.kill('SIGTERM');
        setTimeout(() => {
          if (!proc?.killed) {
            proc?.kill('SIGKILL');
          }
          resolve();
        }, 5000);
      });
    },
    
    isRunning(): boolean {
      return proc !== null && !proc.killed;
    },
  };
}
```

---

## 4. 数据流与控制流

### 4.1 应用启动流程

```
[用户双击图标]
    │
    ▼
[Electron 主进程启动]
    │
    ├──→ 读取 package.json 确认版本
    │
    ├──→ 启动 Python 子进程
    │       │
    │       ├──→ spawn("C:/.../python.exe", ["start_api.py"])
    │       │
    │       └──→ 等待 stdout 中出现 "Uvicorn running"
    │               │
    │               ▼
    │       [后端就绪 @ http://localhost:18000]
    │
    ├──→ 创建 BrowserWindow
    │       │
    │       ├──→ 加载 file://.../index.html（生产模式）
    │       │   或 http://localhost:5173（开发模式）
    │       │
    │       └──→ 注入预加载脚本 preload.js
    │
    └──→ [应用就绪，用户可交互]
```

### 4.2 文件浏览流程（Electron 模式）

```
[用户点击"浏览"按钮]
    │
    ▼
[ChatArea 或 ParamForm]
    │
    ├──→ 调用 selectDirectory() / selectFile()
    │       │
    │       └──→ window.electron.selectDirectory({ defaultPath })
    │               │
    │               ▼
    │       [IPC: dialog:selectDirectory]
    │               │
    │               ▼
    │       [Electron 主进程]
    │               │
    │               ├──→ dialog.showOpenDialog({ properties: ['openDirectory'] })
    │               │
    │               └──→ 用户选择 → 返回 "C:\Users\PC\project"
    │                       │
    │                       ▼
    │       [IPC 返回路径字符串]
    │               │
    │               ▼
    │       [React setState → 调用 API 更新 workspace]
    │
    └──→ [UI 显示完整绝对路径]
```

### 4.3 应用退出流程

```
[用户点击关闭窗口 / Cmd+Q]
    │
    ▼
[app 'before-quit' 事件]
    │
    ├──→ 调用 pythonManager.stop()
    │       │
    │       ├──→ proc.kill('SIGTERM')
    │       │
    │       └──→ 等待 5s → 如未退出则 kill('SIGKILL')
    │
    └──→ [退出 Electron]
```

---

## 5. 依赖关系

### 5.1 向上依赖

| 模块 | 接口 | 用途 |
|------|------|------|
| `frontend/` | React 构建产物 | Electron 加载的 UI |
| `api/` | FastAPI 运行时 | Python 子进程启动的脚本 |
| `core/` | Workspace | 后端路径校验（不直接依赖，通过 HTTP API） |

### 5.2 向下暴露

| 接口 | 使用方 |
|------|--------|
| `window.electron.selectFile()` | `ParamForm.tsx` |
| `window.electron.selectDirectory()` | `ChatArea.tsx`, `ParamForm.tsx` |
| `window.electron.getApiBaseUrl()` | `api/client.ts`, `MainPage.tsx` |

### 5.3 新增依赖

**`frontend/package.json` 新增（`devDependencies`）**:
- `electron` — Electron 运行时
- `electron-builder` — 打包工具
- `@electron/remote`（可选）— 如需要更多主进程交互

**不计入 P5 生产依赖**：Electron 为构建时/分发时依赖，不影响后端运行时依赖锁定。

---

## 6. 异常与错误处理

| 异常场景 | 处理策略 |
|---------|---------|
| Python 后端启动失败（conda 环境不存在） | 弹窗提示："未找到 gis-agent conda 环境，请先运行 `conda env create`" |
| Python 后端启动超时（30s） | 弹窗提示："后端启动超时，请检查端口是否被占用" |
| Python 后端运行中崩溃 | 检测退出码，弹窗提示并尝试重启（最多 3 次） |
| 用户取消文件对话框 | IPC 返回 `null`，前端保持原值不变 |
| 打包后路径解析错误 | 使用 `app.getAppPath()` / `__dirname` 区分开发/生产路径 |

---

## 7. 测试策略

### 7.1 单元测试

| 测试场景 | 验证点 |
|---------|--------|
| IPC handler 注册 | `dialog:selectFile` 和 `dialog:selectDirectory` 已注册 |
| Python 进程启动 | `spawn` 被正确调用，参数包含 start_api.py 路径 |
| Python 进程终止 | `SIGTERM` → 等待 → `SIGKILL` 的清理流程 |
| 路径解析（开发/生产） | `getPythonPath()` / `getScriptPath()` 在两种模式下返回正确路径 |

### 7.2 集成测试

| 测试场景 | 验证点 |
|---------|--------|
| 端到端启动 | Electron 启动 → Python 启动 → 窗口加载 → 前端显示 |
| 文件对话框 | 点击浏览 → 对话框打开 → 选择路径 → 前端显示绝对路径 |
| 后端崩溃恢复 | 强制 kill Python → 前端检测到断开 → 提示用户 |

### 7.3 Mock 策略

- `dialog.showOpenDialog` mock：返回预设的文件路径
- `child_process.spawn` mock：模拟 Python 进程的 stdout/stderr/exit
- `app.getAppPath()` mock：固定为临时目录

---

## 8. 需求追溯表

| 需求 ID | 设计决策 | 代码文件/函数 | 说明 |
|:-------:|:--------:|:-------------:|------|
| F6 | DC-E01, DC-E04 | `electron/main.ts`, `ChatArea.tsx` | 工作空间目录选择返回绝对路径 |
| F7 | DC-E01, DC-E04 | `electron/preload.ts`, `ParamForm.tsx` | 参数文件路径浏览返回绝对路径 |
| UX-1 | DC-E02, DC-E04 | `ParamForm.tsx` | 参数表单浏览按钮调用原生对话框 |
| P3 | DC-E01 | `electron/main.ts:startPythonManager()` | 工作空间路径由后端 Workspace 规范化 |
| P5 | DC-E05 | — | 不引入后端生产依赖，Electron 仅构建依赖 |
| UX-2 | DC-E06 | `TopBar.tsx` | 工作空间路径自适应宽度显示 |
| UX-3 | DC-E07 | `electron/main.ts`, `TopBar.tsx` | 无边框窗口 + 自定义标题栏 + 窗口控制按钮 |

---

## 附录：变更记录

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.2.0 | 2026-05-31 | 新增 DC-E06（工作空间路径自适应）、DC-E07（无边框窗口 + 自定义标题栏 + 窗口控制按钮） |
| v1.1.0 | 2026-05-31 | 废弃浏览器 UI 回退；移除 `isElectron` 字段；新增 `getApiBaseUrl` IPC；后端端口改为从 config.json 动态读取；路由改为 HashRouter |
| v1.0.0 | 2026-05-31 | 初版，定义 Electron 壳 + 独立 Python 后端方案 |
