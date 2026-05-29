import { apiClient } from './client'
import type { PipelineStep, DataLink } from '../types'

export async function previewPipeline(
  steps: PipelineStep[],
  autoLinks: DataLink[]
): Promise<{ script: string; steps: unknown[] }> {
  const resp = await apiClient.post('/pipeline', { steps, autoLinks })
  return resp.data
}

export async function executePipeline(
  steps: PipelineStep[],
  autoLinks: DataLink[]
): Promise<{ execution_id: string; message: string }> {
  const resp = await apiClient.post('/pipeline/execute', { steps, autoLinks })
  return resp.data
}
