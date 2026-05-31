import { app, BrowserWindow, dialog, ipcMain } from 'electron'
import path from 'path'
import { spawn, ChildProcess } from 'child_process'
import fs from 'fs'

// ─── Configuration ───────────────────────────────────────────

const PYTHON_PATH =
  process.platform === 'win32'
    ? 'C:/Users/PC/.conda/envs/gis-agent/python.exe'
    : '/Users/PC/.conda/envs/gis-agent/bin/python'

/**
 * Read API port from backend config.json.
 * Falls back to 18000 (matches config.json default).
 */
function getBackendPort(): number {
  try {
    const configPath = path.join(__dirname, '../../config/config.json')
    const raw = fs.readFileSync(configPath, 'utf-8')
    const cfg = JSON.parse(raw)
    return cfg.api?.port ?? 18000
  } catch {
    return 18000
  }
}

const BACKEND_PORT = getBackendPort()
const BACKEND_URL = `http://localhost:${BACKEND_PORT}`

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
    const scriptPath = path.join(__dirname, '../../start_api.py')

    pythonProcess = spawn(PYTHON_PATH, [scriptPath], {
      cwd: path.join(__dirname, '../..'),
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
}

// ─── App Lifecycle ───────────────────────────────────────────

app.whenReady().then(async () => {
  registerIpcHandlers()

  try {
    await startPythonBackend()
    console.log('[Electron] Python backend started successfully at', BACKEND_URL)
  } catch (err) {
    console.error('[Electron] Failed to start Python backend:', err)
    dialog.showErrorBox(
      '后端启动失败',
      `无法启动 Python 后端服务。请检查：\n1. gis-agent conda 环境已安装\n2. 端口 ${BACKEND_PORT} 未被占用\n3. config.json 配置正确`
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
