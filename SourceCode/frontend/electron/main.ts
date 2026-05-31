import { app, BrowserWindow, dialog, ipcMain } from 'electron'
import path from 'path'
import { spawn, ChildProcess } from 'child_process'

// ─── Configuration ───────────────────────────────────────────

const PYTHON_PATH =
  process.platform === 'win32'
    ? 'C:/Users/PC/.conda/envs/gis-agent/python.exe'
    : '/Users/PC/.conda/envs/gis-agent/bin/python'

const BACKEND_PORT = 8000
const BACKEND_URL = `http://localhost:${BACKEND_PORT}`

// ─── State ───────────────────────────────────────────────────

let mainWindow: BrowserWindow | null = null
let pythonProcess: ChildProcess | null = null

// ─── Window Management ───────────────────────────────────────

function createMainWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 600,
    title: 'GIS Agent',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })

  // Load URL: dev mode uses Vite dev server, production uses built files
  if (process.env.VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL)
    mainWindow.webContents.openDevTools()
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'))
  }

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

// ─── Python Backend Process ──────────────────────────────────

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
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
      windowsHide: true,
    })

    let stdoutBuffer = ''
    let stderrBuffer = ''

    pythonProcess.stdout?.on('data', (data: Buffer) => {
      const text = data.toString()
      stdoutBuffer += text
      console.log(`[Python] ${text.trim()}`)

      // Detect uvicorn startup message
      if (text.includes('Uvicorn running') || text.includes('Application startup complete')) {
        resolve()
      }
    })

    pythonProcess.stderr?.on('data', (data: Buffer) => {
      const text = data.toString()
      stderrBuffer += text
      console.error(`[Python] ${text.trim()}`)
    })

    pythonProcess.on('error', (err: Error) => {
      console.error('[Python] Failed to start:', err.message)
      reject(err)
    })

    pythonProcess.on('exit', (code: number | null) => {
      if (code !== 0 && code !== null) {
        console.error(`[Python] Exited with code ${code}`)
      }
    })

    // Timeout fallback
    setTimeout(() => {
      // If we haven't resolved yet, check if the process is still running
      if (pythonProcess && !pythonProcess.killed) {
        // Try a health check
        checkBackendHealth().then((healthy) => {
          if (healthy) {
            resolve()
          }
        })
      }
    }, 15000)

    // Hard timeout
    setTimeout(() => {
      reject(new Error('Backend startup timeout (30s)'))
    }, 30000)
  })
}

/**
 * Check if the backend is responding.
 */
async function checkBackendHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${BACKEND_URL}/api/templates`)
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
 * Register IPC handlers for file dialogs.
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
}

// ─── App Lifecycle ───────────────────────────────────────────

app.whenReady().then(async () => {
  registerIpcHandlers()

  try {
    await startPythonBackend()
    console.log('[Electron] Python backend started successfully')
  } catch (err) {
    console.error('[Electron] Failed to start Python backend:', err)
    dialog.showErrorBox(
      '后端启动失败',
      '无法启动 Python 后端服务。请检查：\n1. gis-agent conda 环境已安装\n2. 端口 8000 未被占用'
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
