import { contextBridge, ipcRenderer } from 'electron'

export interface ElectronAPI {
  isElectron: boolean
  /** Backend base URL (e.g. http://localhost:18000), only available in Electron */
  apiBaseUrl: string | null
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

contextBridge.exposeInMainWorld('electron', {
  isElectron: true,
  apiBaseUrl: null,

  selectFile: async (
    options?: Parameters<ElectronAPI['selectFile']>[0]
  ): Promise<string | null> => {
    return ipcRenderer.invoke('dialog:selectFile', options)
  },

  selectDirectory: async (
    options?: Parameters<ElectronAPI['selectDirectory']>[0]
  ): Promise<string | null> => {
    return ipcRenderer.invoke('dialog:selectDirectory', options)
  },

  getApiBaseUrl: async (): Promise<string | null> => {
    return ipcRenderer.invoke('app:getApiBaseUrl')
  },
} as ElectronAPI)
