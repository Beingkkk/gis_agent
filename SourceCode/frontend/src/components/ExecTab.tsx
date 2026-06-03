/**
 * ExecTab: 脚本执行 TAB（DC-UX-11）
 *
 * 四种状态：命令预览 → 执行中 → 成功 / 失败
 *
 * Design: DC-UX-11, DC-UX-12
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import CmdEditor from './CmdEditor'
import ExecStatusPanel from './ExecStatusPanel'
import type { ExecResult, ErrorContext, TemplateDetail, ExecEnvVerifyRequest, ExecEnvVerifyResponse, ExecEnvSnapshot } from '../types'

export type ExecPhase = 'preview' | 'executing' | 'success' | 'failure'

interface ExecTabProps {
  /** 当前执行阶段 */
  phase: ExecPhase
  /** 当前显示的命令（可能是用户编辑后的） */
  script: string
  /** 模板名称 */
  templateName?: string | null
  /** 模板详情（用于参数摘要） */
  templateDetail?: TemplateDetail | null
  /** 执行中：日志输出 */
  execLog: string[]
  /** 执行结果（成功/失败态需要） */
  execResult: ExecResult | null
  /** 错误上下文（失败态需要） */
  errorContext: ErrorContext | null
  /** 当前参数值 */
  paramValues?: Record<string, string>
  /** 未填完的必填参数 */
  missingParams?: string[]
  /** 当前执行环境配置 */
  execEnv?: ExecEnvSnapshot | null
  /** 脚本编辑回调 */
  onScriptChange: (script: string) => void
  /** 刷新脚本（根据当前参数重新生成） */
  onRefreshScript: () => void
  /** 执行脚本 */
  onExecute: () => void
  /** 取消执行 */
  onCancelExecute: () => void
  /** 返回修改参数 */
  onEditParams: () => void
  /** 新任务 */
  onNewTask: () => void
  /** 导出脚本 */
  onExportScript?: () => void
  /** 环境验证回调 */
  onVerifyEnv?: (config: ExecEnvVerifyRequest) => Promise<ExecEnvVerifyResponse>
  /** 环境保存回调（返回是否成功保存为默认配置） */
  onSaveEnv?: (config: ExecEnvVerifyRequest) => Promise<boolean>
  /** 获取 conda 环境列表 */
  onListCondaEnvs?: () => Promise<string[]>
}

/** 阶段标签 */
function phaseLabel(phase: ExecPhase): { text: string; color: string } {
  switch (phase) {
    case 'preview':
      return { text: '命令预览', color: 'bg-blue-100 text-blue-700' }
    case 'executing':
      return { text: '执行中', color: 'bg-emerald-100 text-emerald-700' }
    case 'success':
      return { text: '执行成功', color: 'bg-emerald-100 text-emerald-700' }
    case 'failure':
      return { text: '执行失败', color: 'bg-red-100 text-red-700' }
  }
}

export default function ExecTab({
  phase,
  script,
  templateName,
  templateDetail,
  execLog,
  execResult,
  errorContext,
  paramValues,
  missingParams,
  execEnv,
  onScriptChange,
  onRefreshScript,
  onExecute,
  onCancelExecute,
  onEditParams,
  onNewTask,
  onExportScript,
  onVerifyEnv,
  onSaveEnv,
  onListCondaEnvs,
}: ExecTabProps) {
  const [envPanelOpen, setEnvPanelOpen] = useState(false)
  const [envType, setEnvType] = useState<'system' | 'conda'>(execEnv?.type === 'conda' ? 'conda' : 'system')
  const [shellType, setShellType] = useState<string>(execEnv?.shell || 'auto')
  const [envName, setEnvName] = useState<string>(execEnv?.env_name || '')
  const [shellPath, setShellPath] = useState<string>(execEnv?.shell_path || '')
  const [verifyResult, setVerifyResult] = useState<ExecEnvVerifyResponse | null>(null)
  const [verifyLoading, setVerifyLoading] = useState(false)
  const [saveLoading, setSaveLoading] = useState(false)
  const [saveSuccess, setSaveSuccess] = useState(false)
  const [saveDefaultError, setSaveDefaultError] = useState<string | null>(null)
  const [condaEnvs, setCondaEnvs] = useState<string[]>([])
  const hasInitSync = useRef(false)

  /** 首次 execEnv 可用时同步到本地状态（初始化/自动加载默认配置） */
  useEffect(() => {
    if (execEnv && !hasInitSync.current) {
      setEnvType(execEnv.type === 'conda' ? 'conda' : 'system')
      setShellType(execEnv.shell || 'auto')
      setShellPath(execEnv.shell_path || '')
      // env_name only applies to conda; system always clears it
      if (execEnv.type === 'conda') {
        setEnvName(execEnv.env_name || '')
      } else {
        setEnvName('')
      }
      hasInitSync.current = true
    }
  }, [execEnv])

  /** 展开/收起环境面板 */
  const handleToggleEnvPanel = useCallback(async () => {
    const next = !envPanelOpen
    setEnvPanelOpen(next)
    setSaveSuccess(false)
    setSaveDefaultError(null)
    if (next) {
      // 同步非 envName 的配置
      if (execEnv) {
        setEnvType(execEnv.type === 'conda' ? 'conda' : 'system')
        setShellType(execEnv.shell || 'auto')
        setShellPath(execEnv.shell_path || '')
      }
      // Always fetch conda env list (regardless of current type, for switching)
      if (onListCondaEnvs) {
        try {
          const envs = await onListCondaEnvs()
          setCondaEnvs(envs)
          // Match env_name only when current execEnv is conda
          if (execEnv?.type === 'conda') {
            if (execEnv.env_name && envs.includes(execEnv.env_name)) {
              setEnvName(execEnv.env_name)
            } else {
              setEnvName('')
            }
          } else {
            setEnvName('')
          }
        } catch (e) {
          console.error('获取 conda 环境列表失败:', e)
          setCondaEnvs([])
          setEnvName('')
        }
      }
    }
  }, [envPanelOpen, onListCondaEnvs, execEnv])

  const handleVerify = async () => {
    if (!onVerifyEnv) return
    setVerifyLoading(true)
    setVerifyResult(null)
    try {
      const result = await onVerifyEnv({
        type: envType,
        env_name: envName,
        shell: shellType,
        shell_path: shellPath,
      })
      setVerifyResult(result)
    } catch (e) {
      console.error('环境验证失败:', e)
      setVerifyResult({
        valid: false,
        shell: { type: shellType, path: '' },
        gdal: { available: false, version: '' },
        env_vars: {},
        error: '验证请求失败',
      })
    } finally {
      setVerifyLoading(false)
    }
  }

  const handleSave = async () => {
    if (!onSaveEnv) return
    setSaveLoading(true)
    setSaveSuccess(false)
    setSaveDefaultError(null)
    try {
      const defaultSaved = await onSaveEnv({
        type: envType,
        env_name: envName,
        shell: shellType,
        shell_path: shellPath,
      })
      setSaveSuccess(true)
      if (!defaultSaved) {
        setSaveDefaultError('已应用到当前会话，但默认配置保存失败')
      }
      setEnvPanelOpen(false)
    } catch (e) {
      console.error('环境保存失败:', e)
      setSaveSuccess(false)
      setSaveDefaultError('环境保存失败')
    } finally {
      setSaveLoading(false)
    }
  }

  /** 环境配置按钮 */
  const EnvConfigButton = () => {
    const hasEnv = execEnv && execEnv.gdal_available
    return (
      <button
        type="button"
        onClick={handleToggleEnvPanel}
        className={`flex items-center gap-1.5 h-7 px-2.5 rounded-md text-[11px] font-medium border transition-colors flex-shrink-0 ${
          hasEnv
            ? 'bg-emerald-50 text-emerald-600 border-emerald-200 hover:bg-emerald-100'
            : 'bg-white text-slate-500 border-slate-200 hover:bg-blue-50 hover:text-blue-600'
        }`}
        title={hasEnv ? `环境已配置: ${execEnv.shell} | ${execEnv.gdal_version}` : '配置执行环境'}
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12.22 2h-.44a2 2 0 00-2 2v.18a2 2 0 01-1 1.73l-.43.25a2 2 0 01-2 0l-.15-.08a2 2 0 00-2.73.73l-.22.38a2 2 0 00.73 2.73l.15.1a2 2 0 011 1.72v.51a2 2 0 01-1 1.74l-.15.09a2 2 0 00-.73 2.73l.22.38a2 2 0 002.73.73l.15-.08a2 2 0 012 0l.43.25a2 2 0 011 1.73V20a2 2 0 002 2h.44a2 2 0 002-2v-.18a2 2 0 011-1.73l.43-.25a2 2 0 012 0l.15.08a2 2 0 002.73-.73l.22-.39a2 2 0 00-.73-2.73l-.15-.1a2 2 0 01-1-1.72v-.51a2 2 0 011-1.74l.15-.09a2 2 0 00.73-2.73l-.22-.38a2 2 0 00-2.73-.73l-.15.08a2 2 0 01-2 0l-.43-.25a2 2 0 01-1-1.73V4a2 2 0 00-2-2z" />
          <circle cx="12" cy="12" r="3" />
        </svg>
        {hasEnv ? (saveSuccess ? '已保存为默认' : '环境已配置') : '环境设置'}
      </button>
    )
  }

  const label = phaseLabel(phase)

  // ═══════════════════════════════════════════════════════════════
  // 命令预览态
  // ═══════════════════════════════════════════════════════════════
  if (phase === 'preview') {
    const hasMissing = (missingParams?.length ?? 0) > 0

    return (
      <div className="flex flex-col h-full">
        {/* Header */}
        <div className="h-[52px] bg-white border-b border-slate-200 flex items-center justify-between px-5 flex-shrink-0"
        >
          <div className="flex items-center gap-2"
          >
            <span className={`text-[10px] font-semibold px-2 py-[2px] rounded-full ${label.color}`}
            >
              {label.text}
            </span>
            {templateName && (
              <span className="text-[13px] font-medium text-slate-900"
              >
                {templateName}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <EnvConfigButton />
          </div>
        </div>

        {/* Environment Config Panel */}
        {envPanelOpen && (
          <div className="border-b border-slate-200 bg-slate-50 px-5 py-4 space-y-3 flex-shrink-0">
            <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-[0.8px]">
              执行环境配置
            </div>
            <div className="grid grid-cols-2 gap-3">
              {/* Shell type */}
              <div>
                <label className="block text-[11px] text-slate-500 mb-1">Shell 类型</label>
                <select
                  value={shellType}
                  onChange={(e) => {
                    setShellType(e.target.value)
                    setShellPath('')
                  }}
                  className="w-full h-8 px-2 rounded-md border border-slate-200 bg-white text-xs text-slate-700 focus:outline-none focus:border-blue-400"
                >
                  <option value="auto">自动探测</option>
                  <option value="bash">Bash</option>
                  <option value="cmd">CMD</option>
                  <option value="powershell">PowerShell</option>
                </select>
              </div>
              {/* Environment type */}
              <div>
                <label className="block text-[11px] text-slate-500 mb-1">环境类型</label>
                <select
                  value={envType}
                  onChange={async (e) => {
                    const newType = e.target.value as 'system' | 'conda'
                    setEnvType(newType)
                    if (newType === 'conda' && onListCondaEnvs && condaEnvs.length === 0) {
                      try {
                        const envs = await onListCondaEnvs()
                        setCondaEnvs(envs)
                      } catch (err) {
                        console.error('获取 conda 环境列表失败:', err)
                      }
                    }
                    if (newType === 'system') {
                      setEnvName('')
                    }
                  }}
                  className="w-full h-8 px-2 rounded-md border border-slate-200 bg-white text-xs text-slate-700 focus:outline-none focus:border-blue-400"
                >
                  <option value="system">系统默认</option>
                  <option value="conda">Conda 环境</option>
                </select>
              </div>
            </div>
            {/* Conda env name */}
            {envType === 'conda' && (
              <div>
                <label className="block text-[11px] text-slate-500 mb-1">Conda 环境名</label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={envName}
                    onChange={(e) => setEnvName(e.target.value)}
                    placeholder="输入或选择环境名"
                    list="conda-envs"
                    className="flex-1 h-8 px-2 rounded-md border border-slate-200 bg-white text-xs text-slate-700 focus:outline-none focus:border-blue-400"
                  />
                  <datalist id="conda-envs">
                    {condaEnvs.map((env) => (
                      <option key={env} value={env} />
                    ))}
                  </datalist>
                </div>
              </div>
            )}
            {/* Custom shell path */}
            <div>
              <label className="block text-[11px] text-slate-500 mb-1">
                Shell 路径（可选，覆盖自动探测）
              </label>
              <input
                type="text"
                value={shellPath}
                onChange={(e) => setShellPath(e.target.value)}
                placeholder="例如 C:\Program Files\Git\bin\bash.exe"
                className="w-full h-8 px-2 rounded-md border border-slate-200 bg-white text-xs text-slate-700 focus:outline-none focus:border-blue-400"
              />
            </div>
            {/* Actions */}
            <div className="flex gap-2 pt-1">
              <button
                onClick={handleVerify}
                disabled={verifyLoading}
                className="h-8 px-3 rounded-md bg-white border border-slate-200 text-xs font-medium text-slate-600 hover:bg-blue-50 hover:text-blue-600 hover:border-blue-300 transition-colors flex items-center gap-1.5"
              >
                {verifyLoading && (
                  <div className="w-3 h-3 border-2 border-slate-300 border-t-transparent rounded-full animate-spin" />
                )}
                测试环境
              </button>
              <button
                onClick={handleSave}
                disabled={saveLoading || !verifyResult?.valid}
                className={`h-8 px-3 rounded-md text-xs font-medium transition-colors flex items-center gap-1.5 ${
                  verifyResult?.valid
                    ? 'bg-emerald-600 text-white hover:bg-emerald-700'
                    : 'bg-slate-200 text-slate-400 cursor-not-allowed'
                }`}
              >
                {saveLoading && (
                  <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                )}
                保存
              </button>
            </div>
            {/* Verify result */}
            {verifyResult && (
              <div className={`rounded-md px-3 py-2 text-[11px] ${
                verifyResult.valid
                  ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                  : 'bg-red-50 text-red-700 border border-red-200'
              }`}>
                {verifyResult.valid ? (
                  <div className="space-y-0.5">
                    <div>✓ 环境验证通过</div>
                    <div className="text-emerald-600/80">Shell: {verifyResult.shell.type} ({verifyResult.shell.path})</div>
                    <div className="text-emerald-600/80">GDAL: {verifyResult.gdal.version}</div>
                  </div>
                ) : (
                  <div className="space-y-0.5">
                    <div>✗ 环境验证失败</div>
                    {verifyResult.error && (
                      <div className="text-red-600/80">{verifyResult.error}</div>
                    )}
                  </div>
                )}
              </div>
            )}
            {/* Default save error */}
            {saveDefaultError && (
              <div className="rounded-md px-3 py-2 text-[11px] bg-amber-50 text-amber-700 border border-amber-200">
                ⚠ {saveDefaultError}
              </div>
            )}
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-5 py-5 space-y-5"
        >
          {/* CmdEditor */}
          <CmdEditor
            script={script}
            onChange={onScriptChange}
            onRefresh={onRefreshScript}
            missingParams={missingParams}
          />

          {/* Param summary */}
          {templateDetail && templateDetail.params.length > 0 && (
            <div className="rounded-xl border border-slate-200 bg-white overflow-hidden"
            >
              <div className="px-4 py-2.5 bg-slate-50 border-b border-slate-100 flex items-center justify-between"
              >
                <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-[0.8px]"
                >
                  参数摘要
                </span>
                {hasMissing && (
                  <span className="text-[10px] px-2 py-[2px] rounded bg-amber-50 text-amber-600 border border-amber-200"
                  >
                    {missingParams!.length} 个必填参数未填
                  </span>
                )}
              </div>
              <div className="px-4 py-3 space-y-1.5"
              >
                {templateDetail.params.map((p) => {
                  const val = paramValues?.[p.name] ?? ''
                  const isFilled = val !== ''
                  return (
                    <div key={p.name} className="flex items-center gap-2 text-xs"
                    >
                      <span className="text-slate-500 w-[100px] flex-shrink-0 truncate"
                        title={p.name}
                      >
                        {p.name}
                        {p.required && <span className="text-red-400 ml-0.5">*</span>}
                      </span>
                      <span className={`font-mono px-1.5 py-[1px] rounded truncate ${
                        isFilled
                          ? 'text-emerald-700 bg-emerald-50'
                          : p.required
                            ? 'text-red-600 bg-red-50'
                            : 'text-slate-500 bg-slate-50'
                      }`}
                        title={isFilled ? val : p.type}
                      >
                        {isFilled ? val : p.type}
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-2 pt-2"
          >
            <button
              onClick={onExportScript}
              className="h-10 px-4 rounded-xl border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 hover:text-blue-600 hover:border-blue-300 transition-all flex items-center justify-center gap-1.5"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              导出脚本
            </button>
            <button
              onClick={onExecute}
              disabled={hasMissing}
              className={`flex-1 h-10 rounded-xl text-sm font-medium transition-all flex items-center justify-center gap-1.5
                ${hasMissing
                  ? 'bg-slate-200 text-slate-400 cursor-not-allowed'
                  : 'bg-emerald-600 text-white hover:bg-emerald-700 shadow-[0_1px_4px_rgba(16,185,129,0.2)]'
                }`}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
              >
                <polygon points="5 3 19 12 5 21 5 3" />
              </svg>
              {hasMissing ? `还有 ${missingParams!.length} 个必填参数` : '执行脚本'}
            </button>
          </div>
        </div>
      </div>
    )
  }

  // ═══════════════════════════════════════════════════════════════
  // 执行中态
  // ═══════════════════════════════════════════════════════════════
  if (phase === 'executing') {
    return (
      <div className="flex flex-col h-full"
      >
        {/* Header */}
        <div className="h-[52px] bg-white border-b border-slate-200 flex items-center justify-between px-5 flex-shrink-0"
        >
          <div className="flex items-center gap-2"
          >
            <div className="w-4 h-4 border-2 border-emerald-400 border-t-transparent rounded-full animate-spin"
            />
            <span className={`text-[10px] font-semibold px-2 py-[2px] rounded-full ${label.color}`}
            >
              {label.text}
            </span>
            {templateName && (
              <span className="text-[13px] font-medium text-slate-900"
              >
                {templateName}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onCancelExecute}
              className="text-[11px] font-medium px-2.5 py-[5px] rounded-md border border-red-100 text-red-600 hover:bg-red-50 transition-all"
            >
              取消
            </button>
          </div>
        </div>

        {/* Script preview + Terminal output */}
        <div className="flex-1 overflow-hidden flex flex-col"
        >
          {/* Script being executed */}
          {script && (
            <div className="flex-shrink-0 border-b border-slate-200"
            >
              <div className="px-4 py-2 bg-[#1e293b] border-b border-white/[0.06] flex items-center justify-between"
              >
                <span className="text-[11px] font-medium text-slate-400 font-mono"
                >
                  执行命令
                </span>
              </div>
              <div className="bg-[#0f172a] p-4 overflow-x-auto"
              >
                <pre className="text-slate-300 text-xs font-mono leading-relaxed whitespace-pre"
                >
                  {script}
                </pre>
              </div>
            </div>
          )}
          {/* Terminal output */}
          <div className="flex-1 overflow-hidden bg-[#0f172a] flex flex-col min-h-0"
          >
            <div className="px-4 py-2 bg-[#1e293b] border-b border-white/[0.06] flex items-center justify-between flex-shrink-0"
            >
              <span className="text-[11px] font-medium text-slate-400 font-mono"
              >
                执行日志
              </span>
              <span className="text-[10px] text-slate-600"
              >
                {execLog.length} 行
              </span>
            </div>
            <div className="flex-1 overflow-y-auto p-4"
            >
              {execLog.length === 0 ? (
                <div className="text-slate-600 text-xs font-mono"
                >
                  等待执行输出...
                </div>
              ) : (
                <pre className="text-slate-300 text-xs font-mono leading-relaxed whitespace-pre-wrap"
                >
                  {execLog.join('\n')}
                </pre>
              )}
            </div>
          </div>
        </div>
      </div>
    )
  }

  // ═══════════════════════════════════════════════════════════════
  // 成功态 / 失败态
  // ═══════════════════════════════════════════════════════════════
  return (
    <div className="flex flex-col h-full"
    >
      {/* Header */}
      <div className="h-[52px] bg-white border-b border-slate-200 flex items-center justify-between px-5 flex-shrink-0"
      >
        <div className="flex items-center gap-2"
        >
          <span className={`text-[10px] font-semibold px-2 py-[2px] rounded-full ${label.color}`}
          >
            {label.text}
          </span>
          {templateName && (
            <span className="text-[13px] font-medium text-slate-900"
            >
              {templateName}
            </span>
          )}
        </div>
      </div>

      {/* Status panel */}
      <div className="flex-1 overflow-y-auto px-5 py-5"
      >
        {execResult && (
          <ExecStatusPanel
            result={execResult}
            errorContext={errorContext}
            onEditParams={onEditParams}
            onNewTask={onNewTask}
          />
        )}
      </div>
    </div>
  )
}
