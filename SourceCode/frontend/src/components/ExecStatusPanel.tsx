/**
 * ExecStatusPanel: 执行状态面板（DC-UX-11）
 *
 * 展示脚本执行的成功/失败结果。
 *
 * 成功态：绿色卡片 + 结果详情（输出文件、耗时等）
 * 失败态：红色卡片 + 错误输出高亮 + 一键诊断按钮
 *
 * Design: DC-UX-11
 */

import type { ExecResult, ErrorContext } from '../types'

interface ExecStatusPanelProps {
  /** 执行结果 */
  result: ExecResult
  /** 错误上下文（失败时） */
  errorContext?: ErrorContext | null
  /** 一键诊断 */
  onDiagnose?: () => void
  /** 重新执行 */
  onRetry?: () => void
  /** 返回修改参数 */
  onEditParams?: () => void
  /** 新任务 */
  onNewTask?: () => void
}

export default function ExecStatusPanel({
  result,
  errorContext,
  onDiagnose,
  onRetry,
  onEditParams,
  onNewTask,
}: ExecStatusPanelProps) {
  if (result.success) {
    // ═══════════════════════════════════════════════════════════════
    // 成功态
    // ═══════════════════════════════════════════════════════════════
    const durationSec = (result.duration_ms / 1000).toFixed(1)

    return (
      <div className="space-y-4">
        {/* Success banner */}
        <div className="rounded-xl bg-emerald-50 border border-emerald-200 p-4 flex items-start gap-3">
          <div className="w-8 h-8 rounded-full bg-emerald-100 flex items-center justify-center flex-shrink-0">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-emerald-600">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-emerald-800">执行成功</h3>
            <p className="text-xs text-emerald-600 mt-0.5">
              脚本已顺利完成，耗时 {durationSec} 秒
            </p>
          </div>
        </div>

        {/* Result details */}
        <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
          <div className="px-4 py-2.5 bg-slate-50 border-b border-slate-100">
            <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-[0.8px]">结果详情</span>
          </div>
          <div className="px-4 py-3 space-y-2">
            {result.output_path && (
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-500">输出文件</span>
                <span className="font-mono text-slate-700 bg-slate-50 px-2 py-[2px] rounded">{result.output_path}</span>
              </div>
            )}
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-500">返回码</span>
              <span className="font-mono text-emerald-600 bg-emerald-50 px-2 py-[2px] rounded">{result.returncode}</span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-500">执行耗时</span>
              <span className="text-slate-700">{durationSec} 秒</span>
            </div>
          </div>
        </div>

        {/* Stdout preview */}
        {result.stdout && (
          <div>
            <h4 className="text-[11px] font-semibold text-slate-400 uppercase tracking-[0.8px] mb-2">输出内容</h4>
            <div className="bg-[#0f172a] rounded-lg overflow-hidden">
              <pre className="text-slate-300 p-3 text-[11px] font-mono leading-relaxed overflow-x-auto whitespace-pre-wrap max-h-[200px] overflow-y-auto">
                {result.stdout}
              </pre>
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2 pt-2">
          <button
            onClick={onNewTask}
            className="flex-1 h-10 rounded-xl bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-all shadow-[0_1px_4px_rgba(37,99,235,0.2)] flex items-center justify-center gap-1.5"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
            </svg>
            新任务
          </button>
        </div>
      </div>
    )
  }

  // ═══════════════════════════════════════════════════════════════
  // 失败态
  // ═══════════════════════════════════════════════════════════════
  const diagnosis = errorContext?.diagnosis
  const isDiagnosing = diagnosis === null || diagnosis === undefined

  return (
    <div className="space-y-4">
      {/* Failure banner */}
      <div className="rounded-xl bg-red-50 border border-red-200 p-4 flex items-start gap-3">
        <div className="w-8 h-8 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-red-600">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </div>
        <div>
          <h3 className="text-sm font-semibold text-red-800">执行失败</h3>
          <p className="text-xs text-red-600 mt-0.5">
            返回码 {result.returncode}，耗时 {(result.duration_ms / 1000).toFixed(1)} 秒
          </p>
        </div>
      </div>

      {/* Diagnosis result */}
      {diagnosis ? (
        <div className="rounded-xl bg-amber-50 border border-amber-200 p-4">
          <div className="flex items-center gap-2 mb-3">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-amber-600">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="16" x2="12" y2="12" />
              <line x1="12" y1="8" x2="12.01" y2="8" />
            </svg>
            <h3 className="text-sm font-semibold text-amber-800">诊断结果</h3>
          </div>
          <div className="space-y-2">
            <div>
              <span className="text-[11px] font-medium text-amber-600 uppercase">根因</span>
              <p className="text-sm text-amber-700 mt-0.5">{diagnosis.cause}</p>
            </div>
            <div>
              <span className="text-[11px] font-medium text-amber-600 uppercase">建议</span>
              <p className="text-sm text-amber-700 mt-0.5">{diagnosis.suggestion}</p>
            </div>
            {diagnosis.can_auto_fix && (
              <div className="flex items-center gap-1.5 mt-2">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-emerald-500">
                  <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span className="text-xs font-medium text-emerald-700">可自动修复</span>
                {Object.keys(diagnosis.fixed_params).length > 0 && (
                  <span className="text-xs text-emerald-600">
                    ({Object.entries(diagnosis.fixed_params).map(([k, v]) => `${k}=${v}`).join(', ')})
                  </span>
                )}
              </div>
            )}
          </div>
        </div>
      ) : isDiagnosing && errorContext ? (
        <div className="rounded-lg bg-amber-50 border border-amber-200 p-4 flex items-center gap-3">
          <div className="w-5 h-5 border-2 border-amber-400 border-t-transparent rounded-full animate-spin flex-shrink-0" />
          <div>
            <p className="text-sm font-medium text-amber-800">正在分析错误原因...</p>
            <p className="text-xs text-amber-600 mt-0.5">LLM 诊断中，请稍候</p>
          </div>
        </div>
      ) : null}

      {/* Error output */}
      {(result.stderr || result.stdout) && (
        <div>
          <h4 className="text-[11px] font-semibold text-slate-400 uppercase tracking-[0.8px] mb-2">错误输出</h4>
          <div className="bg-[#0f172a] rounded-lg overflow-hidden">
            <pre className="text-slate-300 p-3 text-[11px] font-mono leading-relaxed overflow-x-auto whitespace-pre-wrap max-h-[240px] overflow-y-auto">
              {result.stderr || result.stdout}
            </pre>
          </div>
        </div>
      )}

      {/* Recovery actions */}
      <div className="space-y-2 pt-2">
        <button
          onClick={onDiagnose}
          className="w-full h-10 rounded-xl bg-amber-600 text-white text-sm font-medium hover:bg-amber-700 transition-all shadow-[0_1px_4px_rgba(217,119,6,0.2)] flex items-center justify-center gap-1.5"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="16" x2="12" y2="12" />
            <line x1="12" y1="8" x2="12.01" y2="8" />
          </svg>
          一键诊断
        </button>
        <button
          onClick={onRetry}
          className="w-full h-10 rounded-xl bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-700 transition-all shadow-[0_1px_4px_rgba(16,185,129,0.2)] flex items-center justify-center gap-1.5"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polygon points="5 3 19 12 5 21 5 3" />
          </svg>
          重新执行
        </button>
        <button
          onClick={onEditParams}
          className="w-full h-10 rounded-xl border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-all flex items-center justify-center gap-1.5"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
            <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
          </svg>
          修改参数
        </button>
      </div>
    </div>
  )
}
