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

/** 读取持久化的默认执行环境配置（DC-0106） */
export async function getDefaultExecEnv(): Promise<ExecEnvVerifyRequest | null> {
  try {
    const resp = await apiClient.get('/exec-env/default')
    return resp.data as ExecEnvVerifyRequest
  } catch (e: any) {
    // 204 No Content means no default saved yet
    if (e.response?.status === 204) {
      return null
    }
    throw e
  }
}

/** 保存默认执行环境配置到本地文件（DC-0106） */
export async function saveDefaultExecEnv(
  config: ExecEnvVerifyRequest
): Promise<void> {
  await apiClient.post('/exec-env/default', config)
}
