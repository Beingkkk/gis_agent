import { create } from 'zustand'
import type {
  SessionState,
  SessionSnapshot,
  ChatMessage,
  CandidateTemplate,
  TemplateDef,
  ErrorContext,
  TabId,
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
  errorContext: ErrorContext | null
  isLoading: boolean
  templates: TemplateDef[]
  workspace: string | null

  // === v4: 三 TAB 架构新增状态 (DC-UX-10 ~ DC-UX-13) ===

  /** 当前激活的 TAB */
  activeTab: TabId
  /** GIS 问答 TAB 的独立消息历史（累积，支持清空） */
  qaMessages: ChatMessage[]
  /** 用户在 ExecTab 中编辑后的命令（覆盖 session.script_preview） */
  editedScript: string | null

  setSession: (snapshot: SessionSnapshot) => void
  addMessage: (msg: ChatMessage) => void
  setLoading: (loading: boolean) => void
  setTemplates: (templates: TemplateDef[]) => void
  setWorkspace: (path: string) => void
  reset: () => void

  // === v4: 三 TAB 架构新增方法 ===

  setActiveTab: (tab: TabId) => void
  addQAMessage: (msg: ChatMessage) => void
  clearQAMessages: () => void
  setEditedScript: (script: string | null) => void
}

const initialState = {
  sessionId: null,
  state: 'IDLE' as SessionState,
  taskContext: null,
  messages: [] as ChatMessage[],
  lockedTemplateId: null,
  scriptPreview: null,
  errorContext: null as ErrorContext | null,
  isLoading: false,
  templates: [] as TemplateDef[],
  workspace: null as string | null,
  // v4
  activeTab: 'discovery' as TabId,
  qaMessages: [] as ChatMessage[],
  editedScript: null as string | null,
}

export const useSession = create<SessionStore>((set) => ({
  ...initialState,

  setSession: (snapshot) =>
    set({
      sessionId: snapshot.session_id,
      state: snapshot.state,
      taskContext: snapshot.task_context,
      scriptPreview: snapshot.script_preview,
      errorContext: snapshot.error_context,
      messages: snapshot.history,
      lockedTemplateId: snapshot.task_context.template_id,
      workspace: snapshot.workspace,
      editedScript: snapshot.user_script,
    }),

  addMessage: (msg) =>
    set((state) => ({
      messages: [...state.messages, msg],
    })),

  setLoading: (loading) => set({ isLoading: loading }),

  setTemplates: (templates) => set({ templates }),

  setWorkspace: (path) => set({ workspace: path }),

  reset: () => set(initialState),

  // === v4 methods ===

  setActiveTab: (tab) => set({ activeTab: tab }),

  addQAMessage: (msg) =>
    set((state) => ({
      qaMessages: [...state.qaMessages, msg],
    })),

  clearQAMessages: () => set({ qaMessages: [] }),

  setEditedScript: (script) => set({ editedScript: script }),
}))
