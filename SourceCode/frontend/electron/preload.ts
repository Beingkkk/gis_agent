import { contextBridge, ipcRenderer } from 'electron'

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
  selectFile(options?: {
    title?: string
    defaultPath?: string
    filters?: { name: string; extensions: string[] }[]
  }): Promise<string | null>
  selectDirectory(options?: {
    title?: string
    defaultPath?: string
  }): Promise<string | null>
  saveFile(options?: {
    title?: string
    defaultPath?: string
    filters?: { name: string; extensions: string[] }[]
  }): Promise<string | null>
  showItemInFolder(filePath: string): Promise<void>
  getApiBaseUrl(): Promise<string | null>
  windowControl: WindowControlAPI
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

  saveFile: async (
    options?: Parameters<ElectronAPI['saveFile']>[0]
  ): Promise<string | null> => {
    return ipcRenderer.invoke('dialog:saveFile', options)
  },

  showItemInFolder: async (filePath: string): Promise<void> => {
    return ipcRenderer.invoke('shell:showItemInFolder', filePath)
  },

  getApiBaseUrl: async (): Promise<string | null> => {
    return ipcRenderer.invoke('app:getApiBaseUrl')
  },

  windowControl: {
    minimize: async (): Promise<void> => {
      return ipcRenderer.invoke('window:minimize')
    },
    maximize: async (): Promise<void> => {
      return ipcRenderer.invoke('window:maximize')
    },
    close: async (): Promise<void> => {
      return ipcRenderer.invoke('window:close')
    },
    isMaximized: async (): Promise<boolean> => {
      return ipcRenderer.invoke('window:isMaximized')
    },
    onWindowStateChange: (callback: WindowStateListener): (() => void) => {
      const handler = (_: unknown, state: WindowState) => callback(state)
      ipcRenderer.on('window:state-change', handler)
      return () => {
        ipcRenderer.removeListener('window:state-change', handler)
      }
    },
  },
} as ElectronAPI)
