import { apiClient } from './client'

export interface HealthResponse {
  status: string
}

export async function getHealth(): Promise<HealthResponse> {
  const resp = await apiClient.get('/health')
  return resp.data
}
