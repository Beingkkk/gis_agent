import { contextBridge, ipcRenderer } from 'electron'

export interface ElectronAPI {
  selectFile(options?: {
    title?: string
    defaultPath?: string
    filters?: { name: string; extensions: string[] }[]
  }): Promise<string | null>
  selectDirectory(options?: {
    title?: string
    defaultPath?: string
  }): Promise<string | null>
  getApiBaseUrl(): Promise<string | null>
}

contextBridge.exposeInMainWorld('electron', {
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
