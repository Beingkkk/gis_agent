/**
 * Electron IPC API 封装。
 *
 * 提供文件/目录选择对话框与后端地址的统一入口。
 * 仅在 Electron 渲染进程中可用（通过 preload 注入）。
 *
 * Design: DC-E02, DC-E04
 */

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
