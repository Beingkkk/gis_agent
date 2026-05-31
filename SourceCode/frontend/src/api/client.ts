import axios from 'axios'
import { getApiBaseUrl } from '../electron-api'

export const apiClient = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
})

// Resolve absolute backend URL via IPC and switch axios to it.
// The IPC call is async — until it resolves, relative /api URLs rely on
// Vite dev proxy.
getApiBaseUrl().then((url) => {
  if (url) {
    apiClient.defaults.baseURL = `${url}/api`
  }
})

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
