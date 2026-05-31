/**
 * ExecTab: 脚本执行 TAB（DC-UX-11）
 *
 * 四种状态：命令预览 → 执行中 → 成功 / 失败
 *
 * Design: DC-UX-11, DC-UX-12
 */

import CmdEditor from './CmdEditor'
import ExecStatusPanel from './ExecStatusPanel'
import { selectDirectory } from '../electron-api'
import type { ExecResult, ErrorContext, TemplateDetail } from '../types'

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
  /** 工作空间路径 */
  workspace?: string | null
  /** GDAL bin 目录路径 */
  gdalBin?: string
  /** 脚本编辑回调 */
  onScriptChange: (script: string) => void
  /** 刷新脚本（根据当前参数重新生成） */
  onRefreshScript: () => void
  /** 执行脚本 */
  onExecute: () => void
  /** 取消执行 */
  onCancelExecute: () => void
  /** 一键诊断 */
  onDiagnose: () => void
  /** 重新执行 */
  onRetry: () => void
  /** 返回修改参数 */
  onEditParams: () => void
  /** 新任务 */
  onNewTask: () => void
  /** 切换工作空间 */
  onUpdateWorkspace?: (path: string) => void
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
  workspace,
  gdalBin,
  onScriptChange,
  onRefreshScript,
  onExecute,
  onCancelExecute,
  onDiagnose,
  onRetry,
  onEditParams,
  onNewTask,
  onUpdateWorkspace,
}: ExecTabProps) {
  const handleBrowseClick = async () => {
    const path = await selectDirectory()
    if (path && path !== workspace) {
      onUpdateWorkspace?.(path)
    }
  }

  /** 工作空间路径显示（header 右侧公用） */
  const WorkspaceDisplay = () => (
    <div className="flex items-center gap-3 min-w-0">
      {gdalBin && (
        <div className="flex items-center gap-1 text-[10px] text-slate-400"
          title={`GDAL: ${gdalBin}`}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-emerald-400 flex-shrink-0"
          >
            <path d="M12 2L2 7l10 5 10-5-10-5z" />
            <path d="M2 17l10 5 10-5" />
            <path d="M2 12l10 5 10-5" />
          </svg>
          <span className="font-mono truncate max-w-[120px]">{gdalBin}</span>
        </div>
      )}
      <div className="flex items-center gap-1.5 text-xs min-w-0 overflow-x-auto scrollbar-hide">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-blue-400 flex-shrink-0">
          <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z" />
        </svg>
        <span className="font-mono text-slate-600 text-xs whitespace-nowrap" title={workspace || '未设置'}>
          {workspace || '未设置'}
        </span>
      </div>
      <button
        type="button"
        onClick={handleBrowseClick}
        className="h-7 px-2.5 rounded-md bg-white text-slate-500 text-[11px] hover:bg-blue-50 hover:text-blue-600 hover:border-blue-300 transition-colors border border-slate-200 font-medium flex-shrink-0"
      >
        浏览
      </button>
    </div>
  )
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
          <WorkspaceDisplay />
        </div>

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
            <button
              onClick={onEditParams}
              className="h-10 rounded-xl border border-slate-200 px-4 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-all flex items-center justify-center gap-1.5"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
              >
                <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
                <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
              </svg>
              修改参数
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
            <WorkspaceDisplay />
            <button
              onClick={onCancelExecute}
              className="text-[11px] font-medium px-2.5 py-[5px] rounded-md border border-red-100 text-red-600 hover:bg-red-50 transition-all"
            >
              取消
            </button>
          </div>
        </div>

        {/* Terminal output */}
        <div className="flex-1 overflow-hidden bg-[#0f172a] flex flex-col max-h-[400px]"
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
        <WorkspaceDisplay />
      </div>

      {/* Status panel */}
      <div className="flex-1 overflow-y-auto px-5 py-5"
      >
        {execResult && (
          <ExecStatusPanel
            result={execResult}
            errorContext={errorContext}
            onDiagnose={onDiagnose}
            onRetry={onRetry}
            onEditParams={onEditParams}
            onNewTask={onNewTask}
          />
        )}
      </div>
    </div>
  )
}
