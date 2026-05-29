import { apiClient } from './client'
import type { GeneratedTemplate } from '../types'

export interface GenerateConfig {
  category?: string
  tool_source?: string
}

export async function generateTemplate(
  documentText: string,
  config: GenerateConfig
): Promise<GeneratedTemplate> {
  const resp = await apiClient.post('/generator/generate', {
    document_text: documentText,
    config,
  })
  return resp.data
}

export async function validateTemplate(body: string): Promise<{ valid: boolean; errors: string[] }> {
  const resp = await apiClient.post('/generator/validate', { body })
  return resp.data
}

export async function saveTemplate(
  templateId: string,
  body: string,
  overwrite = false
): Promise<{ saved_path: string }> {
  const resp = await apiClient.post('/generator/save', {
    template_id: templateId,
    body,
    overwrite,
  })
  return resp.data
}
