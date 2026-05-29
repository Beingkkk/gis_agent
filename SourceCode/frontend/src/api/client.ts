import axios from 'axios'

export const apiClient = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
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
