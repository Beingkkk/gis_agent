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
    setSession,
    addMessage,
    setLoading,
    setTemplates,
  } = useSession()

  const [inputText, setInputText] = useState('')
  const [selectedTemplate, setSelectedTemplate] = useState<TemplateDetail | null>(null)
  const [execLog, setExecLog] = useState<string[]>([])
  const [isExecuting, setIsExecuting] = useState(false)
  const { connect: connectExec } = useWebSocket()
  const chatBottomRef = useRef<HTMLDivElement>(null)

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

  // Scroll chat to bottom
  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, execLog])

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
    addMessage({ role: 'user', content: text })
    setLoading(true)

    try {
      const result = await processIntent(sessionId, text)
      setSession(result)

      // Add agent response based on state
      if (result.state === 'INTENT_CONFIRM') {
        const candidates = result.task_context.candidates || []
        addMessage({
          role: 'agent',
          content: `找到 ${candidates.length} 个候选模板，请点击确认：`,
          type: 'cards',
          meta: { candidates },
        })
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
      } else {
        addMessage({
          role: 'agent',
          content: '请从左栏选择一个模板开始。',
          type: 'text',
        })
      }
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
    // Just switch state visually; params remain in taskContext
    if (sessionId && selectedTemplate) {
      lockTemplate(sessionId, selectedTemplate.id)
        .then((s) => setSession(s))
        .catch(() => {})
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
      state={state}
      leftPanel={
        <div className="p-4">
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">
            模板
          </h2>
          <TemplateCardList
            templates={templates}
            selectedId={selectedTemplate?.id || null}
            onSelect={handleSelectTemplate}
          />
        </div>
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
        onSelectTemplate={handleSelectFromChat}
      />

      {/* Input area */}
      <div className="border-t border-gray-200 bg-white p-3">
        <div className="flex gap-2">
          <input
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              state === 'PARAM_COLLECT'
                ? '在右栏填写参数...'
                : '输入需求，如"shp转geojson"...'
            }
            disabled={isLoading || isExecuting}
            className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:bg-gray-50"
          />
          <button
            onClick={handleSend}
            disabled={isLoading || isExecuting || !inputText.trim()}
            className="rounded-md bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
          >
            发送
          </button>
        </div>
      </div>
    </Layout>
  )
}
