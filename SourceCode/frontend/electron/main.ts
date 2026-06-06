import { app, BrowserWindow, dialog, ipcMain, shell } from 'electron'
import path from 'path'
import { spawn, spawnSync, ChildProcess } from 'child_process'
import fs from 'fs'
import os from 'os'

// ─── Configuration ───────────────────────────────────────────

const BACKEND_PORT = 18000
const BACKEND_URL = `http://localhost:${BACKEND_PORT}`

/**
 * Resolve Python executable path with fallback chain.
 *
 * Explicit config (env var / config.json) takes precedence and is returned
 * as-is.  When auto-discovering, every candidate is dependency-checked and
 * the first one with all required packages wins.
 *
 * Design: DC-E03
 */
function resolvePythonPath(): string | null {
  const isWin = process.platform === 'win32'
  const exeName = isWin ? 'python.exe' : 'python'

  // 1. Environment variable — explicit, return as-is
  const envPath = process.env.GISAGENT_PYTHON_PATH
  if (envPath && fs.existsSync(envPath)) {
    return envPath
  }

  // 2. config.json → python_path — explicit, return as-is
  try {
    const configPath = path.join(APP_ROOT, 'config', 'config.json')
    if (fs.existsSync(configPath)) {
      const raw = fs.readFileSync(configPath, 'utf-8')
      const cfg = JSON.parse(raw)
      if (cfg.python_path && fs.existsSync(cfg.python_path)) {
        return cfg.python_path
      }
    }
  } catch {
    // ignore parse errors
  }

  // 3. Auto-discover — collect ALL candidates, then pick first with deps
  const candidates: string[] = []

  // 3a. System PATH
  const pathNames = isWin
    ? ['python.exe', 'python3.exe']
    : ['python3', 'python']
  for (const name of pathNames) {
    const found = findInPath(name)
    if (found) candidates.push(found)
  }

  // 3b. Common conda / anaconda directories
  const home = os.homedir()
  const condaDirs: string[] = []
  if (isWin) {
    condaDirs.push(
      path.join(home, '.conda', 'envs'),
      path.join(home, 'anaconda3', 'envs'),
      path.join(home, 'miniconda3', 'envs'),
      'C:\\ProgramData\\anaconda3\\envs',
      'C:\\ProgramData\\miniconda3\\envs',
    )
  } else {
    condaDirs.push(
      path.join(home, '.conda', 'envs'),
      path.join(home, 'anaconda3', 'envs'),
      path.join(home, 'miniconda3', 'envs'),
      '/opt/conda/envs',
    )
  }

  for (const envsDir of condaDirs) {
    if (!fs.existsSync(envsDir)) continue
    try {
      const envs = fs.readdirSync(envsDir, { withFileTypes: true })
      for (const entry of envs) {
        if (!entry.isDirectory()) continue
        const pythonExe = path.join(envsDir, entry.name, exeName)
        if (fs.existsSync(pythonExe)) {
          candidates.push(pythonExe)
        }
      }
    } catch {
      // ignore permission errors
    }
  }

  // Deduplicate while preserving order
  const seen = new Set<string>()
  for (const p of candidates) {
    if (seen.has(p)) continue
    seen.add(p)
    if (verifyPythonDeps(p) === null) {
      return p
    }
  }

  // Fallback: return first candidate even if deps missing (error dialog will guide user)
  return candidates[0] ?? null
}

/**
 * Find an executable name in the system PATH.
 */
function findInPath(name: string): string | null {
  const isWin = process.platform === 'win32'
  const pathDirs = (process.env.PATH || '').split(isWin ? ';' : ':')
  for (const dir of pathDirs) {
    if (!dir) continue
    const full = path.join(dir, name)
    if (fs.existsSync(full)) {
      return full
    }
  }
  return null
}

/**
 * Verify that the found Python has the required packages installed.
 */
function verifyPythonDeps(pythonPath: string): string | null {
  try {
    const result = spawnSync(pythonPath, [
      '-c',
      'import fastapi, uvicorn, jinja2, pydantic, anthropic; print("OK")',
    ], { encoding: 'utf-8', timeout: 5000 })
    if (result.status === 0 && result.stdout.includes('OK')) {
      return null
    }
    return result.stderr || '缺少必需的 Python 依赖包'
  } catch (err: any) {
    return err.message || '依赖验证失败'
  }
}

/**
 * Resolve the application root directory for locating Python backend resources.
 *
 * Design: DC-E03
 *   - Dev mode:  __dirname is dist-electron/, root is ../../ (SourceCode/)
 *   - Packaged:  resources live in a SourceCode/ sibling of the exe so that
 *     Python's Path(__file__) hard-coded traversals remain valid.
 */
function resolveAppRoot(): string {
  if (!app.isPackaged) {
    return path.join(__dirname, '../..')
  }
  return path.join(path.dirname(app.getPath('exe')), 'SourceCode')
}

const APP_ROOT = resolveAppRoot()

// ─── State ───────────────────────────────────────────────────

let mainWindow: BrowserWindow | null = null
let pythonProcess: ChildProcess | null = null

// ─── Window Management ───────────────────────────────────────

/** Wait for Vite dev server to be ready before loading. */
async function waitForDevServer(url: string, timeoutMs: number = 30000): Promise<boolean> {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(url)
      if (res.ok) return true
    } catch {
      // not ready yet
    }
    await new Promise((r) => setTimeout(r, 1000))
  }
  return false
}

function createMainWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 600,
    title: 'GIS Agent',
    frame: false,
    titleBarStyle: 'hidden',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })

  // Load URL: dev mode uses Vite dev server, production uses built files
  if (!app.isPackaged) {
    const devServerUrl = 'http://localhost:5173'
    waitForDevServer(devServerUrl).then((ready) => {
      if (ready && mainWindow) {
        mainWindow.loadURL(devServerUrl)
        mainWindow.webContents.openDevTools()
      } else if (mainWindow) {
        dialog.showErrorBox(
          '开发服务器未启动',
          `无法在 30 秒内连接到 ${devServerUrl}。\n请确保 Vite dev server 已运行（npm run dev）。`
        )
      }
    })
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'))
  }

  // Forward window state changes to renderer for maximize button sync
  mainWindow.on('maximize', () => {
    mainWindow?.webContents.send('window:state-change', { isMaximized: true })
  })
  mainWindow.on('unmaximize', () => {
    mainWindow?.webContents.send('window:state-change', { isMaximized: false })
  })
  // Also notify on resize (e.g. Aero Snap on Windows triggers neither maximize nor unmaximize directly)
  mainWindow.on('resize', () => {
    mainWindow?.webContents.send('window:state-change', {
      isMaximized: mainWindow?.isMaximized() ?? false,
    })
  })

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

// ─── Python Backend Process ──────────────────────────────────

/**
 * Detect if a log line indicates uvicorn has started.
 */
function isStartupMessage(text: string): boolean {
  return text.includes('Uvicorn running') || text.includes('Application startup complete')
}

/**
 * Start the Python FastAPI backend as a child process.
 *
 * Design: DC-E03
 */
function startPythonBackend(): Promise<void> {
  return new Promise((resolve, reject) => {
    const pythonPath = resolvePythonPath()
    if (!pythonPath) {
      reject(new Error('未找到 Python 解释器'))
      return
    }

    // resolvePythonPath() already validates deps for auto-discovered candidates,
    // but fallback may return a candidate with missing deps — double-check here.
    const depError = verifyPythonDeps(pythonPath)
    if (depError) {
      reject(
        new Error(
          `Python 依赖检查失败 (${path.basename(pythonPath)})\n${depError}`,
        ),
      )
      return
    }

    console.log('[Electron] Using Python:', pythonPath)

    const scriptPath = path.join(APP_ROOT, 'start_api.py')

    pythonProcess = spawn(pythonPath, [scriptPath], {
      cwd: APP_ROOT,
      env: {
        ...process.env,
        PYTHONIOENCODING: 'utf-8',
        ELECTRON_MODE: '1',
      },
      windowsHide: true,
    })

    let resolved = false

    const tryResolve = () => {
      if (!resolved) {
        resolved = true
        resolve()
      }
    }

    pythonProcess.stdout?.on('data', (data: Buffer) => {
      const text = data.toString()
      console.log(`[Python] ${text.trim()}`)

      if (isStartupMessage(text)) {
        tryResolve()
      }
    })

    pythonProcess.stderr?.on('data', (data: Buffer) => {
      const text = data.toString()
      console.error(`[Python] ${text.trim()}`)

      // Uvicorn logs INFO to stderr on some platforms (e.g. Windows)
      if (isStartupMessage(text)) {
        tryResolve()
      }
    })

    pythonProcess.on('error', (err: Error) => {
      console.error('[Python] Failed to start:', err.message)
      if (!resolved) {
        resolved = true
        reject(err)
      }
    })

    pythonProcess.on('exit', (code: number | null) => {
      if (code !== 0 && code !== null) {
        console.error(`[Python] Exited with code ${code}`)
      }
    })

    // Fallback: poll health endpoint after 8s
    const healthInterval = setInterval(() => {
      if (resolved) {
        clearInterval(healthInterval)
        return
      }
      checkBackendHealth().then((healthy) => {
        if (healthy) {
          clearInterval(healthInterval)
          tryResolve()
        }
      })
    }, 2000)

    // Stop polling after 25s
    setTimeout(() => clearInterval(healthInterval), 25000)

    // Hard timeout
    setTimeout(() => {
      if (!resolved) {
        resolved = true
        reject(new Error(`Backend startup timeout (30s). Check port ${BACKEND_PORT} and conda env.`))
      }
    }, 30000)
  })
}

/**
 * Check if the backend is responding.
 */
async function checkBackendHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${BACKEND_URL}/health`)
    return response.ok
  } catch {
    return false
  }
}

/**
 * Stop the Python backend process gracefully.
 */
function stopPythonBackend(): Promise<void> {
  return new Promise((resolve) => {
    if (!pythonProcess || pythonProcess.killed) {
      resolve()
      return
    }

    // Send SIGTERM (or taskkill on Windows)
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', String(pythonProcess.pid), '/f', '/t'])
    } else {
      pythonProcess.kill('SIGTERM')
    }

    // Force kill after 5 seconds
    setTimeout(() => {
      if (pythonProcess && !pythonProcess.killed) {
        if (process.platform === 'win32') {
          try {
            process.kill(Number(pythonProcess.pid), 'SIGKILL')
          } catch {
            // ignore
          }
        } else {
          pythonProcess.kill('SIGKILL')
        }
      }
      resolve()
    }, 5000)
  })
}

// ─── IPC Handlers ────────────────────────────────────────────

/**
 * Register IPC handlers for file dialogs and backend info.
 *
 * Design: DC-E02
 */
function registerIpcHandlers(): void {
  ipcMain.handle(
    'dialog:selectFile',
    async (_, options?: { title?: string; defaultPath?: string; filters?: { name: string; extensions: string[] }[] }) => {
      if (!mainWindow) return null
      const result = await dialog.showOpenDialog(mainWindow, {
        ...options,
        properties: ['openFile'],
      })
      return result.canceled ? null : result.filePaths[0]
    }
  )

  ipcMain.handle(
    'dialog:selectDirectory',
    async (_, options?: { title?: string; defaultPath?: string }) => {
      if (!mainWindow) return null
      const result = await dialog.showOpenDialog(mainWindow, {
        ...options,
        properties: ['openDirectory'],
      })
      return result.canceled ? null : result.filePaths[0]
    }
  )

  ipcMain.handle(
    'dialog:saveFile',
    async (_, options?: { title?: string; defaultPath?: string; filters?: { name: string; extensions: string[] }[] }) => {
      if (!mainWindow) return null
      const result = options
        ? await dialog.showSaveDialog(mainWindow, options)
        : await dialog.showSaveDialog(mainWindow)
      return result.canceled ? null : result.filePath
    }
  )

  // Expose backend URL so renderer can construct absolute API URLs
  ipcMain.handle('app:getApiBaseUrl', () => BACKEND_URL)

  // Window control handlers (DC-E07)
  ipcMain.handle('window:minimize', () => {
    mainWindow?.minimize()
  })

  ipcMain.handle('window:maximize', () => {
    if (mainWindow?.isMaximized()) {
      mainWindow.unmaximize()
    } else {
      mainWindow?.maximize()
    }
  })

  ipcMain.handle('window:close', () => {
    mainWindow?.close()
  })

  ipcMain.handle('window:isMaximized', () => {
    return mainWindow?.isMaximized() ?? false
  })

  // Show file in folder (DC-UX-11a: auto-reveal exported script)
  ipcMain.handle('shell:showItemInFolder', (_, filePath: string) => {
    shell.showItemInFolder(filePath)
  })
}

// ─── App Lifecycle ───────────────────────────────────────────

app.whenReady().then(async () => {
  registerIpcHandlers()

  try {
    await startPythonBackend()
    console.log('[Electron] Python backend started successfully at', BACKEND_URL)
  } catch (err) {
    console.error('[Electron] Failed to start Python backend:', err)
    const isDev = !app.isPackaged
    const detected = resolvePythonPath()
    const detectedInfo = detected
      ? `检测到的 Python: ${detected}`
      : '未检测到 Python 解释器'
    const pythonHelp = isDev
      ? '开发模式: 请确保当前 conda 环境已激活 (gis-agent)'
      : `生产模式: 请确保目标电脑已安装 Python 3.11+ 及依赖包。\n\nPython 搜索顺序:\n1. 环境变量 GISAGENT_PYTHON_PATH\n2. config.json → python_path\n3. 系统 PATH 中的 python/python3\n4. 常见 conda/anaconda 环境目录\n\n快速修复:\n- 设置环境变量: GISAGENT_PYTHON_PATH=C:\\path\\to\\python.exe\n- 或在 config.json 中添加: "python_path": "C:\\\\path\\\\to\\\\python.exe"`
    dialog.showErrorBox(
      '后端启动失败',
      `${err instanceof Error ? err.message : String(err)}\n\n${detectedInfo}\n\n${pythonHelp}\n\n端口: ${BACKEND_PORT}`
    )
  }

  createMainWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createMainWindow()
    }
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('before-quit', async (event) => {
  event.preventDefault()
  await stopPythonBackend()
  app.exit(0)
})
