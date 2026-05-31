import { useEffect, useState, useCallback, useMemo } from 'react'
import Layout from '../components/Layout'
import TopBar from '../components/TopBar'
import TabBar from '../components/TabBar'
import DiscoveryTab from '../components/DiscoveryTab'
import QATab from '../components/QATab'
import ExecTab from '../components/ExecTab'
import DetailPanel from '../components/DetailPanel'
import { useSession } from '../hooks/useSession'
import { useWebSocket } from '../hooks/useWebSocket'
import {
  createSession,
  getSession,
  processIntent,
  chatQuestion,
  lockTemplate,
  submitParams,
  clearSession,
  updateWorkspace,
  diagnoseSession,
  executeScript,
} from '../api/session'
import { listTemplates, getTemplate } from '../api/templates'
import { getApiBaseUrl } from '../electron-api'
import type { TemplateDef, TemplateDetail, ExecResult } from '../types'

export default function MainPage() {
  const {
    sessionId,
    state,
    taskContext,
    templates,
    scriptPreview,
    errorContext,
    isLoading,
    workspace,
    activeTab,
    qaMessages,
    editedScript,
    setSession,
    setLoading,
    setTemplates,
    setWorkspace,
    setActiveTab,
    addQAMessage,
    clearQAMessages,
    setEditedScript,
  } = useSession()

  const [selectedTemplate, setSelectedTemplate] = useState<TemplateDetail | null>(null)
  const [execLog, setExecLog] = useState<string[]>([])
  const [isExecuting, setIsExecuting] = useState(false)
  const [execResult, setExecResult] = useState<ExecResult | null>(null)
  const { connect: connectExec } = useWebSocket()

  // ─── Init: create session + load templates ──────────────────────
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

  // ─── Auto-switch TAB based on state (DC-UX-02) ──────────────────
  useEffect(() => {
    if (state === 'SCRIPT_PREVIEW' || state === 'EXECUTING' || state === 'ERROR_RECOVERY') {
      setActiveTab('exec')
    }
  }, [state, setActiveTab])

  // ─── Compute exec phase ─────────────────────────────────────────
  const execPhase = useMemo(() => {
    if (isExecuting) return 'executing'
    if (state === 'SCRIPT_PREVIEW') return 'preview'
    if (execResult) {
      return execResult.success ? 'success' : 'failure'
    }
    return 'preview'
  }, [isExecuting, state, execResult])

  // ─── Load template detail ───────────────────────────────────────
  const handleSelectTemplate = useCallback(
    async (template: TemplateDef) => {
      if (!sessionId) return
      try {
        const detail = await getTemplate(template.id)
        setSelectedTemplate(detail)
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

  // ─── DiscoveryTab: send intent ──────────────────────────────────
  const handleDiscoverySend = async (text: string) => {
    if (!text.trim() || !sessionId) return

    setLoading(true)
    try {
      const result = await processIntent(sessionId, text)
      setSession(result)

      // v4-UX: INTENT_CONFIRM 候选由用户手动选择后才加载详情
      // PARAM_COLLECT 保持自动加载，否则 DetailPanel 无法渲染参数表单
      if (result.state === 'PARAM_COLLECT') {
        if (result.task_context.template_id) {
          const detail = await getTemplate(result.task_context.template_id)
          setSelectedTemplate(detail)
        }
      } else if (result.state === 'IDLE') {
        // Exploratory Q&A reply → route to QATab
        const lastAgentMsg = result.history.filter((m) => m.role === 'assistant').pop()
        if (lastAgentMsg) {
          addQAMessage({ role: 'user', content: text })
          addQAMessage(lastAgentMsg)
          setActiveTab('qa')
        }
      }
    } catch (e) {
      console.error('意图处理失败:', e)
    } finally {
      setLoading(false)
    }
  }

  // ─── QATab: send message ────────────────────────────────────────
  const handleQASend = async (text: string) => {
    if (!text.trim() || !sessionId) return

    addQAMessage({ role: 'user', content: text })
    setLoading(true)

    try {
      const result = await chatQuestion(sessionId, text)
      setSession(result)
      const lastAgentMsg = result.history.filter((m) => m.role === 'assistant').pop()
      if (lastAgentMsg) {
        addQAMessage(lastAgentMsg)
      }
    } catch (e) {
      addQAMessage({
        role: 'assistant',
        content: '处理失败，请重试。',
        type: 'error',
      })
    } finally {
      setLoading(false)
    }
  }

  // ─── Select candidate from DiscoveryTab ─────────────────────────
  const handleSelectCandidate = async (templateId: string) => {
    if (!sessionId) return
    try {
      const result = await lockTemplate(sessionId, templateId)
      setSession(result)
      const detail = await getTemplate(templateId)
      setSelectedTemplate(detail)
    } catch (e) {
      console.error('锁定模板失败:', e)
    }
  }

  // ─── Submit params ──────────────────────────────────────────────
  const handleSubmitParams = async (params: Record<string, string>) => {
    if (!sessionId) return
    try {
      const result = await submitParams(sessionId, params)
      setSession(result)
      setEditedScript(null)
    } catch (e) {
      console.error('参数提交失败:', e)
    }
  }

  // ─── Execute script via WebSocket ───────────────────────────────
  const handleExecute = async () => {
    if (!sessionId) return
    setIsExecuting(true)
    setExecLog([])
    setExecResult(null)

    // Submit user-edited script to backend before execution (DC-UX-11)
    if (editedScript) {
      try {
        await executeScript(sessionId, false, editedScript)
      } catch (e) {
        console.error('提交编辑脚本失败:', e)
        setIsExecuting(false)
        return
      }
    }

    const backendUrl = await getApiBaseUrl()
    if (!backendUrl) {
      setExecLog((prev) => [...prev, '❌ 无法获取后端地址'])
      setIsExecuting(false)
      return
    }
    const wsBase = backendUrl.replace(/^http/, 'ws')
    const wsUrl = `${wsBase}/ws/execute/${sessionId}`

    connectExec(wsUrl, {
      onMessage: (data) => {
        try {
          const msg = JSON.parse(data)
          if (msg.type === 'output') {
            setExecLog((prev) => [...prev, msg.line || ''])
          } else if (msg.type === 'done') {
            setIsExecuting(false)
            const result: ExecResult = {
              success: msg.success,
              returncode: msg.returncode || 0,
              stdout: msg.stdout || execLog.join('\n'),
              stderr: msg.stderr || '',
              duration_ms: msg.duration_ms || 0,
              output_path: msg.output_path,
            }
            setExecResult(result)
            setExecLog((prev) => [
              ...prev,
              msg.success
                ? '✅ 执行完成'
                : `❌ 执行失败 (返回码: ${msg.returncode || '未知'})`,
            ])
            if (sessionId) {
              getSession(sessionId)
                .then((snapshot) => {
                  setSession(snapshot)
                  if (!msg.success) {
                    if (
                      snapshot.error_context?.diagnosis === null ||
                      snapshot.error_context?.diagnosis === undefined
                    ) {
                      diagnoseSession(sessionId)
                        .then((diagnosed) => {
                          setSession(diagnosed)
                        })
                        .catch((e) => console.error('诊断失败:', e))
                    }
                  }
                })
                .catch((e) => console.error('刷新会话状态失败:', e))
            }
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

  // ─── One-click diagnose (DC-UX-12) ──────────────────────────────
  const handleDiagnose = async () => {
    if (!sessionId || !errorContext) return

    clearQAMessages()
    setActiveTab('qa')

    addQAMessage({
      role: 'assistant',
      content: '🔍 **一键诊断**\n\n正在分析模板信息、执行命令和错误输出...',
      type: 'text',
    })

    try {
      const result = await diagnoseSession(sessionId)
      setSession(result)
      if (result.error_context?.diagnosis) {
        const d = result.error_context.diagnosis
        let content = `**根因：** ${d.cause}\n\n**建议：** ${d.suggestion}`
        if (d.can_auto_fix && Object.keys(d.fixed_params).length > 0) {
          content += `\n\n**可自动修复的参数：** ${Object.entries(d.fixed_params)
            .map(([k, v]) => `${k}=${v}`)
            .join(', ')}`
        }
        addQAMessage({ role: 'assistant', content, type: 'text' })
      } else {
        addQAMessage({
          role: 'assistant',
          content: '诊断完成，但未返回详细结果。',
          type: 'text',
        })
      }
    } catch (e) {
      addQAMessage({
        role: 'assistant',
        content: '诊断失败，请重试。',
        type: 'error',
      })
    }
  }

  // ─── Cancel / reset ─────────────────────────────────────────────
  const handleCancel = async () => {
    if (!sessionId) return
    try {
      const result = await clearSession(sessionId)
      setSession(result)
      setSelectedTemplate(null)
      setExecLog([])
      setExecResult(null)
      setEditedScript(null)
    } catch (e) {
      console.error('清空会话失败:', e)
    }
  }

  // ─── Return to param editing ────────────────────────────────────
  const handleEditParams = () => {
    if (sessionId && selectedTemplate) {
      lockTemplate(sessionId, selectedTemplate.id)
        .then((s) => setSession(s))
        .catch(() => {})
    }
  }

  // ─── New task ───────────────────────────────────────────────────
  const handleNewTask = () => {
    handleCancel()
    setActiveTab('discovery')
  }

  // ─── Refresh script preview ─────────────────────────────────────
  const handleRefreshScript = () => {
    if (sessionId && taskContext?.params) {
      submitParams(sessionId, taskContext.params)
        .then((r) => {
          setSession(r)
          setEditedScript(null)
        })
        .catch(console.error)
    }
  }

  // ─── Update workspace ───────────────────────────────────────────
  const handleUpdateWorkspace = async (path: string) => {
    if (!sessionId) return
    try {
      const result = await updateWorkspace(sessionId, path)
      setSession(result)
      if (result.workspace) {
        setWorkspace(result.workspace)
      }
    } catch (e) {
      console.error('切换工作空间失败:', e)
    }
  }

  // ─── Render ─────────────────────────────────────────────────────
  return (
    <div className="h-screen flex flex-col">
      <TopBar state={state} />
      <div className="flex-1 overflow-hidden">
        <Layout
          mainPanel={
            <div className="flex flex-col h-full">
              <TabBar
                activeTab={activeTab}
                qaMessageCount={qaMessages.length}
                onTabChange={setActiveTab}
              />
              <div className="flex-1 overflow-hidden">
                {activeTab === 'discovery' && (
                  <DiscoveryTab
                    templates={templates}
                    selectedId={state === 'PARAM_COLLECT' ? null : (selectedTemplate?.id || null)}
                    candidates={taskContext?.candidates || []}
                    state={state}
                    isLoading={isLoading}
                    onSelectTemplate={handleSelectTemplate}
                    onSelectCandidate={handleSelectCandidate}
                    onSendIntent={handleDiscoverySend}
                  />
                )}
                {activeTab === 'qa' && (
                  <QATab
                    messages={qaMessages}
                    isLoading={isLoading}
                    lockedTemplateName={taskContext?.template_name}
                    onSendMessage={handleQASend}
                    onClearMessages={clearQAMessages}
                  />
                )}
                {activeTab === 'exec' && (
                  <ExecTab
                    phase={execPhase}
                    script={editedScript || scriptPreview || ''}
                    templateName={taskContext?.template_name}
                    templateDetail={selectedTemplate || undefined}
                    execLog={execLog}
                    execResult={execResult}
                    errorContext={errorContext}
                    missingParams={taskContext?.missing_params}
                    workspace={workspace}
                    onScriptChange={setEditedScript}
                    onRefreshScript={handleRefreshScript}
                    onExecute={handleExecute}
                    onCancelExecute={() => setIsExecuting(false)}
                    onDiagnose={handleDiagnose}
                    onRetry={() => {
                      setExecResult(null)
                      handleExecute()
                    }}
                    onEditParams={handleEditParams}
                    onNewTask={handleNewTask}
                    onUpdateWorkspace={handleUpdateWorkspace}
                  />
                )}
              </div>
            </div>
          }
          rightPanel={
            <DetailPanel
              state={state}
              templateDetail={selectedTemplate}
              paramValues={taskContext?.params || {}}
              workspace={workspace}
              scriptPreview={scriptPreview}
              errorContext={errorContext}
              onLockTemplate={(id) =>
                sessionId && lockTemplate(sessionId, id).then(setSession)
              }
              onSubmitParams={handleSubmitParams}
              onExecute={handleExecute}
              onEditParams={handleEditParams}
              onCancel={handleCancel}
            />
          }
        />
      </div>
    </div>
  )
}
