import { apiClient } from './client'
import type {
  ExecEnvVerifyRequest,
  ExecEnvVerifyResponse,
  SessionSnapshot,
} from '../types'

export async function verifyExecEnv(
  config: ExecEnvVerifyRequest
): Promise<ExecEnvVerifyResponse> {
  const resp = await apiClient.post('/exec-env/verify', config)
  return resp.data
}

export async function setSessionExecEnv(
  sessionId: string,
  config: ExecEnvVerifyRequest
): Promise<SessionSnapshot> {
  const resp = await apiClient.post(`/session/${sessionId}/exec-env`, config)
  return resp.data
}

export async function listCondaEnvs(): Promise<string[]> {
  const resp = await apiClient.get('/exec-env/conda-envs')
  return resp.data.envs
}
