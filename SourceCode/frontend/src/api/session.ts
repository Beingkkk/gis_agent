import { apiClient } from './client'
import type { SessionSnapshot } from '../types'

export async function createSession(
  workspace?: string
): Promise<SessionSnapshot> {
  const resp = await apiClient.post('/session', null, {
    params: workspace ? { workspace } : undefined,
  })
  return resp.data
}

export async function processIntent(
  sessionId: string,
  input: string
): Promise<SessionSnapshot> {
  const resp = await apiClient.post(`/session/${sessionId}/intent`, { input })
  return resp.data
}

export async function lockTemplate(
  sessionId: string,
  templateId: string
): Promise<SessionSnapshot> {
  const resp = await apiClient.post(`/session/${sessionId}/lock`, {
    template_id: templateId,
  })
  return resp.data
}

export async function submitParams(
  sessionId: string,
  params: Record<string, string>
): Promise<SessionSnapshot> {
  const resp = await apiClient.post(`/session/${sessionId}/params`, { params })
  return resp.data
}

export async function executeScript(
  sessionId: string,
  dryRun = false
): Promise<{ execution_id: string }> {
  const resp = await apiClient.post(
    `/session/${sessionId}/execute`,
    null,
    { params: { dry_run: dryRun } }
  )
  return resp.data
}

export async function clearSession(sessionId: string): Promise<SessionSnapshot> {
  const resp = await apiClient.post(`/session/${sessionId}/clear`)
  return resp.data
}

export async function updateWorkspace(
  sessionId: string,
  path: string
): Promise<SessionSnapshot> {
  const resp = await apiClient.post(`/session/${sessionId}/workspace`, {
    path,
  })
  return resp.data
}
