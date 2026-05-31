/**
 * Electron IPC API 封装。
 *
 * 提供文件/目录选择对话框、后端地址与窗口控制的统一入口。
 * 仅在 Electron 渲染进程中可用（通过 preload 注入）。
 *
 * Design: DC-E02, DC-E04, DC-E07
 */

export interface WindowState {
  isMaximized: boolean
}

export type WindowStateListener = (state: WindowState) => void

export interface WindowControlAPI {
  minimize(): Promise<void>
  maximize(): Promise<void>
  close(): Promise<void>
  isMaximized(): Promise<boolean>
  onWindowStateChange(callback: WindowStateListener): () => void
}

export interface ElectronAPI {
  /** Async getter for backend base URL (IPC call to main process) */
  getApiBaseUrl(): Promise<string | null>
  selectFile(options?: {
    title?: string
    defaultPath?: string
    filters?: { name: string; extensions: string[] }[]
  }): Promise<string | null>
  selectDirectory(options?: {
    title?: string
    defaultPath?: string
  }): Promise<string | null>
  windowControl: WindowControlAPI
}

declare global {
  interface Window {
    electron?: ElectronAPI
  }
}

/**
 * 打开文件选择对话框。
 *
 * @param options - 对话框选项
 * @returns 选中的文件绝对路径，用户取消则返回 null
 */
export async function selectFile(options?: {
  title?: string
  defaultPath?: string
  filters?: { name: string; extensions: string[] }[]
}): Promise<string | null> {
  if (window.electron) {
    return window.electron.selectFile(options)
  }
  return null
}

/**
 * 打开目录选择对话框。
 *
 * @param options - 对话框选项
 * @returns 选中的目录绝对路径，用户取消则返回 null
 */
export async function selectDirectory(options?: {
  title?: string
  defaultPath?: string
}): Promise<string | null> {
  if (window.electron) {
    return window.electron.selectDirectory(options)
  }
  return null
}

/**
 * 获取后端 API 基础地址。
 *
 * 返回如 http://localhost:18000，用于构造绝对 API 和 WebSocket URL。
 */
export async function getApiBaseUrl(): Promise<string | null> {
  if (window.electron?.getApiBaseUrl) {
    return window.electron.getApiBaseUrl()
  }
  return null
}

// ─── Window Control (DC-E07) ─────────────────────────────────

/**
 * 最小化窗口。
 */
export async function minimizeWindow(): Promise<void> {
  await window.electron?.windowControl?.minimize()
}

/**
 * 最大化或还原窗口。
 */
export async function maximizeWindow(): Promise<void> {
  await window.electron?.windowControl?.maximize()
}

/**
 * 关闭窗口。
 */
export async function closeWindow(): Promise<void> {
  await window.electron?.windowControl?.close()
}

/**
 * 查询窗口是否已最大化。
 */
export async function isWindowMaximized(): Promise<boolean> {
  return (await window.electron?.windowControl?.isMaximized()) ?? false
}

/**
 * 注册窗口状态变化监听器。
 *
 * 主进程在窗口最大化/还原/resize 时主动推送状态，
 * 确保前端最大化按钮图标与窗口实际状态实时同步。
 *
 * @param callback - 状态变化回调
 * @returns 取消监听的函数
 */
export function onWindowStateChange(callback: WindowStateListener): () => void {
  if (window.electron?.windowControl?.onWindowStateChange) {
    return window.electron.windowControl.onWindowStateChange(callback)
  }
  return () => {}
}
