/**
 * Electron IPC API 封装。
 *
 * 提供文件/目录选择对话框的统一入口。
 * 非 Electron 环境（浏览器）下返回 null，由调用方回退到手动输入。
 *
 * Design: DC-E02, DC-E04
 */

export interface ElectronAPI {
  isElectron: boolean
  /** Backend base URL (e.g. http://localhost:18000), only available in Electron */
  apiBaseUrl: string | null
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
 * 检测当前是否运行在 Electron 环境中。
 */
export function isElectron(): boolean {
  return window.electron?.isElectron === true
}

/**
 * 打开文件选择对话框。
 *
 * @param options - 对话框选项
 * @returns 选中的文件绝对路径，用户取消则返回 null；非 Electron 环境返回 null
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
 * @returns 选中的目录绝对路径，用户取消则返回 null；非 Electron 环境返回 null
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
 * 仅在 Electron 环境下有效，返回如 http://localhost:18000。
 * 浏览器环境下返回 null（由调用方使用相对路径 /api）。
 */
export async function getApiBaseUrl(): Promise<string | null> {
  if (window.electron?.getApiBaseUrl) {
    return window.electron.getApiBaseUrl()
  }
  return null
}
