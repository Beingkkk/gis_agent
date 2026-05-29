import { apiClient } from './client'
import type { TemplateDef, TemplateDetail } from '../types'

export async function listTemplates(): Promise<TemplateDef[]> {
  const resp = await apiClient.get('/templates')
  return resp.data
}

export async function getTemplate(templateId: string): Promise<TemplateDetail> {
  const resp = await apiClient.get(`/templates/${templateId}`)
  return resp.data
}
