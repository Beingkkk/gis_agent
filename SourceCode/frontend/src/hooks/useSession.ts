import { create } from 'zustand'
import type {
  SessionState,
  SessionSnapshot,
  ChatMessage,
  CandidateTemplate,
  TemplateDef,
} from '../types'

interface SessionStore {
  sessionId: string | null
  state: SessionState
  taskContext: {
    template_id: string | null
    template_name: string | null
    params: Record<string, string>
    missing_params: string[]
    candidates: CandidateTemplate[]
  } | null
  messages: ChatMessage[]
  lockedTemplateId: string | null
  scriptPreview: string | null
  isLoading: boolean
  templates: TemplateDef[]

  setSession: (snapshot: SessionSnapshot) => void
  addMessage: (msg: ChatMessage) => void
  setLoading: (loading: boolean) => void
  setTemplates: (templates: TemplateDef[]) => void
  reset: () => void
}

const initialState = {
  sessionId: null,
  state: 'IDLE' as SessionState,
  taskContext: null,
  messages: [] as ChatMessage[],
  lockedTemplateId: null,
  scriptPreview: null,
  isLoading: false,
  templates: [] as TemplateDef[],
}

export const useSession = create<SessionStore>((set) => ({
  ...initialState,

  setSession: (snapshot) =>
    set({
      sessionId: snapshot.session_id,
      state: snapshot.state,
      taskContext: snapshot.task_context,
      scriptPreview: snapshot.script_preview,
      messages: snapshot.history,
      lockedTemplateId: snapshot.task_context.template_id,
    }),

  addMessage: (msg) =>
    set((state) => ({
      messages: [...state.messages, msg],
    })),

  setLoading: (loading) => set({ isLoading: loading }),

  setTemplates: (templates) => set({ templates }),

  reset: () => set(initialState),
}))
