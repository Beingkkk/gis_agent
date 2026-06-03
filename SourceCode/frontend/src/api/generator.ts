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

export interface SaveResult {
  saved_path: string
  category: string
  template_id: string
}

export async function saveTemplate(
  templateId: string,
  body: string,
  overwrite = false
): Promise<SaveResult> {
  const resp = await apiClient.post('/generator/save', {
    template_id: templateId,
    body,
    overwrite,
  })
  return resp.data
}

export interface FileItem {
  content: string
  file_type: string
}

export interface FileResult {
  file_type: string
  raw_chars: number
  cleaned_chars: number
}

export interface ParseDocumentResult {
  files: FileResult[]
  document_text: string
  total_raw_chars: number
  total_cleaned_chars: number
  estimated_tokens: number
}

export async function parseDocument(files: FileItem[]): Promise<ParseDocumentResult> {
  const resp = await apiClient.post('/generator/parse-document', { files })
  return resp.data
}
