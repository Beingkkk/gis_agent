import axios from 'axios'
import { isElectron, getApiBaseUrl } from '../electron-api'

export const apiClient = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
})

// Electron: resolve absolute backend URL and switch axios to it.
// The IPC call is async — until it resolves, relative /api URLs rely on
// Vite dev proxy (dev) or will fail (production from file://).
if (isElectron()) {
  getApiBaseUrl().then((url) => {
    if (url) {
      apiClient.defaults.baseURL = `${url}/api`
    }
  })
}

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 404) {
      console.error('API 404:', error.config?.url)
    } else if (error.response?.status >= 500) {
      console.error('API Server Error:', error.response?.data)
    }
    return Promise.reject(error)
  }
)
