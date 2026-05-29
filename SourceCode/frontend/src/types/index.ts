export type SessionState =
  | 'IDLE'
  | 'INTENT_CONFIRM'
  | 'PARAM_COLLECT'
  | 'SCRIPT_PREVIEW'
  | 'EXECUTING'
  | 'ERROR_RECOVERY'

export interface CandidateTemplate {
  id: string
  name: string
  description: string
}

export interface SessionSnapshot {
  session_id: string
  state: SessionState
  task_context: {
    template_id: string | null
    template_name: string | null
    params: Record<string, string>
    missing_params: string[]
    candidates: CandidateTemplate[]
  }
  script_preview: string | null
  error_context: ErrorContext | null
  history: ChatMessage[]
  workspace: string
}

export interface ChatMessage {
  role: 'user' | 'agent'
  content: string
  type?: 'text' | 'cards' | 'script' | 'timeline' | 'error'
  meta?: Record<string, unknown>
}

export interface ErrorContext {
  message: string
  cause?: string
  suggestion?: string
}

export interface TemplateDef {
  id: string
  name: string
  description: string
  category: string
  tool_source: string
  tags: string[]
}

export interface ParamDef {
  name: string
  type: string
  required: boolean
  description: string
  default?: string
}

export interface ConceptItem {
  term: string
  explanation: string
}

export interface CommonErrorItem {
  error_text: string
  cause: string
  fix: string
}

export interface TemplateDetail extends TemplateDef {
  params: ParamDef[]
  concepts: ConceptItem[]
  notes: string[]
  common_errors: CommonErrorItem[]
  seealso: string[]
}

export interface PipelineStep {
  order: number
  template_id: string
  params: Record<string, string>
}

export interface DataLink {
  fromStep: number
  fromParam: string
  toStep: number
  toParam: string
}

export interface GeneratedTemplate {
  template_id: string
  name: string
  description: string
  body: string
  params: ParamDef[]
  concepts: string[]
  notes: string[]
}
