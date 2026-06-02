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

export async function getSession(sessionId: string): Promise<SessionSnapshot> {
  const resp = await apiClient.get(`/session/${sessionId}`)
  return resp.data
}

export async function processIntent(
  sessionId: string,
  input: string
): Promise<SessionSnapshot> {
  const resp = await apiClient.post(`/session/${sessionId}/intent`, { input })
  return resp.data
}

export async function chatQuestion(
  sessionId: string,
  input: string
): Promise<SessionSnapshot> {
  const resp = await apiClient.post(`/session/${sessionId}/chat`, { input })
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
  dryRun = false,
  script?: string
): Promise<{ execution_id: string }> {
  const resp = await apiClient.post(
    `/session/${sessionId}/execute`,
    null,
    { params: { dry_run: dryRun, script } }
  )
  return resp.data
}

export async function clearSession(sessionId: string): Promise<SessionSnapshot> {
  const resp = await apiClient.post(`/session/${sessionId}/clear`)
  return resp.data
}

export async function diagnoseSession(
  sessionId: string
): Promise<SessionSnapshot> {
  const resp = await apiClient.post(`/session/${sessionId}/diagnose`)
  return resp.data
}

export async function exportScript(
  sessionId: string,
  outputPath: string,
  script?: string
): Promise<{ success: boolean; path: string; size: number; message: string }> {
  const resp = await apiClient.post(`/session/${sessionId}/export-script`, {
    output_path: outputPath,
    script,
  })
  return resp.data
}
