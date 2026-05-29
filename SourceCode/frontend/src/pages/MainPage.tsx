import { useEffect, useState, useCallback, useRef } from 'react'
import Layout from '../components/Layout'
import ChatArea from '../components/ChatArea'
import TemplateCardList from '../components/TemplateCardList'
import DetailPanel from '../components/DetailPanel'
import { useSession } from '../hooks/useSession'
import { useWebSocket } from '../hooks/useWebSocket'
import {
  createSession,
  processIntent,
  lockTemplate,
  submitParams,
  clearSession,
  updateWorkspace,
} from '../api/session'
import { listTemplates, getTemplate } from '../api/templates'
import type { TemplateDef, TemplateDetail } from '../types'

export default function MainPage() {
  const {
    sessionId,
    state,
    taskContext,
    messages,
    templates,
    scriptPreview,
    isLoading,
    workspace,
    setSession,
    addMessage,
    setLoading,
    setTemplates,
    setWorkspace,
  } = useSession()

  const [inputText, setInputText] = useState('')
  const [selectedTemplate, setSelectedTemplate] = useState<TemplateDetail | null>(null)
  const [execLog, setExecLog] = useState<string[]>([])
  const [isExecuting, setIsExecuting] = useState(false)
  const { connect: connectExec } = useWebSocket()
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current
    if (el) {
      el.style.height = 'auto'
      el.style.height = Math.min(el.scrollHeight, 120) + 'px'
    }
  }, [inputText])

  // Initialize: create session + load templates
  useEffect(() => {
    const init = async () => {
      try {
        const session = await createSession()
        setSession(session)
        const list = await listTemplates()
        setTemplates(list)
      } catch (e) {
        console.error('初始化失败:', e)
      }
    }
    init()
  }, [setSession, setTemplates])

  // Load template detail when selected
  const handleSelectTemplate = useCallback(
    async (template: TemplateDef) => {
      if (!sessionId) return
      try {
        const detail = await getTemplate(template.id)
        setSelectedTemplate(detail)
        // If in IDLE or INTENT_CONFIRM, lock the template
        if (state === 'IDLE' || state === 'INTENT_CONFIRM') {
          const updated = await lockTemplate(sessionId, template.id)
          setSession(updated)
        }
      } catch (e) {
        console.error('加载模板详情失败:', e)
      }
    },
    [sessionId, state, setSession]
  )

  // Handle user text input
  const handleSend = async () => {
    if (!inputText.trim() || !sessionId) return

    const text = inputText.trim()
    setInputText('')
    setLoading(true)

    try {
      const result = await processIntent(sessionId, text)
      setSession(result)

      // Only add extra UI message for states that need it
      // IDLE responses are already in result.history from backend
      if (result.state === 'INTENT_CONFIRM') {
        const candidates = result.task_context.candidates || []
        if (candidates.length > 0) {
          addMessage({
            role: 'agent',
            content: `找到 ${candidates.length} 个候选模板，请点击确认：`,
            type: 'cards',
            meta: { candidates },
          })
        }
      } else if (result.state === 'PARAM_COLLECT') {
        addMessage({
          role: 'agent',
          content: `已选择模板「${result.task_context.template_name}」，请在右栏填写参数。`,
          type: 'text',
        })
        // Load template detail for param form
        if (result.task_context.template_id) {
          const detail = await getTemplate(result.task_context.template_id)
          setSelectedTemplate(detail)
        }
      }
      // IDLE (exploratory Q&A): history already contains backend reply, no extra message needed
    } catch (e) {
      addMessage({
        role: 'agent',
        content: '处理失败，请重试。',
        type: 'error',
      })
    } finally {
      setLoading(false)
    }
  }

  // Handle template selection from chat cards
  const handleSelectFromChat = async (templateId: string) => {
    if (!sessionId) return
    try {
      const result = await lockTemplate(sessionId, templateId)
      setSession(result)
      const detail = await getTemplate(templateId)
      setSelectedTemplate(detail)
      addMessage({
        role: 'agent',
        content: `已选择「${detail.name}」，请在右栏填写参数。`,
        type: 'text',
      })
    } catch (e) {
      console.error('锁定模板失败:', e)
    }
  }

  // Submit params
  const handleSubmitParams = async (params: Record<string, string>) => {
    if (!sessionId) return
    try {
      const result = await submitParams(sessionId, params)
      setSession(result)
      if (result.script_preview) {
        addMessage({
          role: 'agent',
          content: result.script_preview,
          type: 'script',
        })
      }
    } catch (e) {
      addMessage({
        role: 'agent',
        content: '参数验证失败: ' + String(e),
        type: 'error',
      })
    }
  }

  // Execute script via WebSocket
  const handleExecute = () => {
    if (!sessionId || !scriptPreview) return
    setIsExecuting(true)
    setExecLog([])

    const wsUrl = `ws://localhost:8000/ws/execute/${sessionId}`
    connectExec(wsUrl, {
      onMessage: (data) => {
        try {
          const msg = JSON.parse(data)
          if (msg.type === 'chunk' || msg.type === 'output') {
            setExecLog((prev) => [...prev, msg.content || msg.data || ''])
          } else if (msg.type === 'done') {
            setIsExecuting(false)
            setExecLog((prev) => [
              ...prev,
              msg.success
                ? `✅ 执行完成${msg.output_path ? ` (输出: ${msg.output_path})` : ''}`
                : `❌ 执行失败: ${msg.error || '未知错误'}`,
            ])
          } else if (msg.type === 'error') {
            setExecLog((prev) => [...prev, `❌ ${msg.message || '错误'}`])
          }
        } catch {
          setExecLog((prev) => [...prev, data])
        }
      },
      onClose: () => {
        setIsExecuting(false)
      },
      onError: () => {
        setExecLog((prev) => [...prev, '❌ WebSocket 连接失败'])
        setIsExecuting(false)
      },
    })
  }

  // Cancel / reset
  const handleCancel = async () => {
    if (!sessionId) return
    try {
      const result = await clearSession(sessionId)
      setSession(result)
      setSelectedTemplate(null)
      setExecLog([])
    } catch (e) {
      console.error('清空会话失败:', e)
    }
  }

  // Return to param editing
  const handleEditParams = () => {
    if (sessionId && selectedTemplate) {
      lockTemplate(sessionId, selectedTemplate.id)
        .then((s) => setSession(s))
        .catch(() => {})
    }
  }

  // Update workspace path
  const handleUpdateWorkspace = async (path: string) => {
    if (!sessionId) return
    try {
      const result = await updateWorkspace(sessionId, path)
      setSession(result)
      setSelectedTemplate(null)
      setExecLog([])
      // Use absolute path returned by backend
      if (result.workspace) {
        setWorkspace(result.workspace)
      }
    } catch (e) {
      console.error('切换工作空间失败:', e)
      addMessage({
        role: 'agent',
        content: '切换工作空间失败: ' + String(e),
        type: 'error',
      })
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <Layout
      leftPanel={
        <TemplateCardList
          templates={templates}
          selectedId={selectedTemplate?.id || null}
          onSelect={handleSelectTemplate}
        />
      }
      rightPanel={
        <DetailPanel
          state={state}
          templateDetail={selectedTemplate}
          paramValues={taskContext?.params || {}}
          scriptPreview={scriptPreview}
          onLockTemplate={(id) =>
            sessionId && lockTemplate(sessionId, id).then(setSession)
          }
          onSubmitParams={handleSubmitParams}
          onExecute={handleExecute}
          onEditParams={handleEditParams}
          onCancel={handleCancel}
        />
      }
    >
      <ChatArea
        messages={[
          ...messages,
          ...(isExecuting || execLog.length > 0
            ? [
                {
                  role: 'agent' as const,
                  content:
                    execLog.length > 0
                      ? execLog.join('\n')
                      : '执行中...',
                  type: 'script' as const,
                },
              ]
            : []),
        ]}
        state={state}
        isLoading={isLoading}
        workspace={workspace}
        onSelectTemplate={handleSelectFromChat}
        onClearSession={handleCancel}
        onUpdateWorkspace={handleUpdateWorkspace}
      />

      {/* Input area */}
      <div className="border-t border-slate-200 bg-white px-5 py-3 flex-shrink-0">
        <div className="flex gap-2 items-end bg-white border border-slate-200 rounded-2xl px-3 py-1.5 shadow-sm focus-within:border-blue-500 focus-within:shadow-[0_0_0_3px_rgba(37,99,235,0.08),0_1px_3px_rgba(0,0,0,0.06)] transition-all">
          <textarea
            ref={textareaRef}
            rows={1}
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              state === 'PARAM_COLLECT'
                ? '在右栏填写参数...'
                : '描述需求，如"shp转geojson"...'
            }
            disabled={isLoading || isExecuting}
            className="flex-1 border-none outline-none resize-none text-sm leading-relaxed py-2 bg-transparent text-slate-900 min-h-[22px] max-h-[120px] disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={isLoading || isExecuting || !inputText.trim()}
            className="w-8 h-8 rounded-[10px] bg-blue-600 text-white flex items-center justify-center flex-shrink-0 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-[0_1px_4px_rgba(37,99,235,0.2)]"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        </div>
        <p className="text-[11px] text-slate-400 mt-2 text-center">
          按 Enter 发送，Shift + Enter 换行
        </p>
      </div>
    </Layout>
  )
}
