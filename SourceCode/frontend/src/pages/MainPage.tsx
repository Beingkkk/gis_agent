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
  lockTemplate,
  submitParams,
  clearSession,
  clearQAHistory,
  diagnoseSession,
  executeScript,
  exportScript,
} from '../api/session'
import { listTemplates, getTemplate } from '../api/templates'
import {
  verifyExecEnv,
  setSessionExecEnv,
  listCondaEnvs,
} from '../api/execEnv'
import { getApiBaseUrl, saveFile, showItemInFolder } from '../electron-api'
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
    activeTab,
    qaMessages,
    editedScript,
    execEnv,
    setSession,
    setLoading,
    setTemplates,
    setActiveTab,
    addQAMessage,
    updateLastQAMessage,
    clearQAMessages,
    setEditedScript,
  } = useSession()

  const [selectedTemplate, setSelectedTemplate] = useState<TemplateDetail | null>(null)
  const [execLog, setExecLog] = useState<string[]>([])
  const [isExecuting, setIsExecuting] = useState(false)
  const [execResult, setExecResult] = useState<ExecResult | null>(null)
  const { connect: connectExec } = useWebSocket()

  // ─── Init: create session + load templates ───────────────────────
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

  // ─── QATab: send message via WebSocket (DC-UX-04) ───────────────
  const [qaStreaming, setQaStreaming] = useState(false)

  const handleQASend = async (text: string) => {
    if (!text.trim() || !sessionId || qaStreaming) return

    addQAMessage({ role: 'user', content: text })
    addQAMessage({ role: 'assistant', content: '' })
    setQaStreaming(true)
    setLoading(true)

    try {
      const backendUrl = await getApiBaseUrl()
      if (!backendUrl) {
        throw new Error('无法获取后端地址')
      }
      const wsBase = backendUrl.replace(/^http/, 'ws')
      const wsUrl = `${wsBase}/ws/chat/${sessionId}`

      const ws = new WebSocket(wsUrl)
      let fullContent = ''

      ws.onopen = () => {
        ws.send(JSON.stringify({ message: text }))
      }

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)
          if (msg.type === 'chunk') {
            fullContent += msg.content
            updateLastQAMessage(fullContent)
          } else if (msg.type === 'done') {
            updateLastQAMessage(fullContent)
            setQaStreaming(false)
            setLoading(false)
            ws.close()
          } else if (msg.type === 'error') {
            updateLastQAMessage(`处理失败：${msg.message}`)
            setQaStreaming(false)
            setLoading(false)
            ws.close()
          }
        } catch {
          // ignore malformed ws messages
        }
      }

      ws.onerror = () => {
        updateLastQAMessage('WebSocket 连接失败，请重试。')
        setQaStreaming(false)
        setLoading(false)
      }

      ws.onclose = () => {
        // 总是重置状态：闭包中的 qaStreaming 永远是初始值 false，
        // 条件判断会导致异常断网时 isLoading 永久卡住 (DC-UX-04)
        setQaStreaming(false)
        setLoading(false)
      }
    } catch (e) {
      updateLastQAMessage('处理失败，请重试。')
      setQaStreaming(false)
      setLoading(false)
    }
  }

  // ─── QATab: clear messages (backend + frontend) ─────────────────
  const handleClearQAMessages = useCallback(async () => {
    if (!sessionId) return
    try {
      await clearQAHistory(sessionId)
      clearQAMessages()
    } catch (e) {
      console.error('清空问答历史失败:', e)
    }
  }, [sessionId, clearQAMessages])

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
              stdout: msg.stdout ?? '',
              stderr: msg.stderr ?? '',
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
                    const hasDiagnosis =
                      snapshot.error_context?.diagnosis !== null &&
                      snapshot.error_context?.diagnosis !== undefined
                    console.log('[诊断] error_context:', snapshot.error_context)
                    console.log('[诊断] hasDiagnosis:', hasDiagnosis)
                    if (!hasDiagnosis) {
                      console.log('[诊断] 触发 diagnoseSession')
                      diagnoseSession(sessionId)
                        .then((diagnosed) => {
                          console.log('[诊断] diagnoseSession 成功:', diagnosed.error_context?.diagnosis)
                          setSession(diagnosed)
                        })
                        .catch((e) => console.error('[诊断] diagnoseSession 失败:', e))
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
      setExecResult(null)
      setExecLog([])
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

  // ─── Exec env: verify ───────────────────────────────────────────
  const handleVerifyEnv = async (config: { type: string; env_name: string; shell: string; shell_path: string }) => {
    return verifyExecEnv(config)
  }

  // ─── Exec env: save ─────────────────────────────────────────────
  const handleSaveEnv = async (config: { type: string; env_name: string; shell: string; shell_path: string }) => {
    if (!sessionId) return
    const result = await setSessionExecEnv(sessionId, config)
    setSession(result)
  }

  // ─── Exec env: list conda envs ──────────────────────────────────
  const handleListCondaEnvs = async () => {
    return listCondaEnvs()
  }

  // ─── Export script (DC-UX-11a) ──────────────────────────────────
  const handleExportScript = async () => {
    if (!sessionId || !taskContext?.template_id) return

    // Determine default filename and filter based on execEnv shell
    const shell = execEnv?.shell || 'cmd'
    const extMap: Record<string, string> = {
      bash: '.sh',
      cmd: '.bat',
      powershell: '.ps1',
    }
    const ext = extMap[shell] || '.bat'
    const timestamp = Math.floor(Date.now() / 1000)
    const defaultFilename = `script_${taskContext.template_id}_${timestamp}${ext}`

    const filtersMap: Record<string, { name: string; extensions: string[] }[]> = {
      bash: [{ name: 'Shell Script', extensions: ['sh'] }],
      cmd: [{ name: 'Batch File', extensions: ['bat'] }],
      powershell: [{ name: 'PowerShell Script', extensions: ['ps1'] }],
    }

    const outputPath = await saveFile({
      title: '导出脚本',
      defaultPath: defaultFilename,
      filters: filtersMap[shell] || filtersMap.cmd,
    })

    if (!outputPath) return

    try {
      // Pass user-edited script content so backend writes verbatim
      const result = await exportScript(sessionId, outputPath, editedScript || undefined)
      if (result.success) {
        setExecLog((prev) => [...prev, `✅ 脚本已导出: ${result.path} (${result.size} bytes)`])
        // Auto-reveal exported file in file manager
        showItemInFolder(result.path)
      }
    } catch (e) {
      console.error('导出脚本失败:', e)
      setExecLog((prev) => [...prev, `❌ 导出失败: ${e}`])
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
                    lockedTemplateName={taskContext?.template_name}
                    onSelectTemplate={handleSelectTemplate}
                    onSelectCandidate={handleSelectCandidate}
                    onSendIntent={handleDiscoverySend}
                  />
                )}
                {activeTab === 'qa' && (
                  <QATab
                    messages={qaMessages}
                    isLoading={isLoading}
                    isStreaming={qaStreaming}
                    lockedTemplateName={taskContext?.template_name}
                    onSendMessage={handleQASend}
                    onClearMessages={handleClearQAMessages}
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
                    paramValues={taskContext?.params || {}}
                    missingParams={taskContext?.missing_params}
                    execEnv={execEnv}
                    onScriptChange={setEditedScript}
                    onRefreshScript={handleRefreshScript}
                    onExecute={handleExecute}
                    onCancelExecute={() => setIsExecuting(false)}
                    onEditParams={handleEditParams}
                    onNewTask={handleNewTask}
                    onExportScript={handleExportScript}
                    onVerifyEnv={handleVerifyEnv}
                    onSaveEnv={handleSaveEnv}
                    onListCondaEnvs={handleListCondaEnvs}
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
              errorContext={errorContext}
              onLockTemplate={(id) =>
                sessionId && lockTemplate(sessionId, id).then(setSession)
              }
              onSubmitParams={handleSubmitParams}
              onCancel={handleCancel}
            />
          }
        />
      </div>
    </div>
  )
}
