import type { TemplateDetail } from '../types'
import ParamForm from './ParamForm'
import ScriptPreview from './ScriptPreview'

interface DetailPanelProps {
  state: string
  templateDetail: TemplateDetail | null
  paramValues: Record<string, string>
  scriptPreview: string | null
  onLockTemplate: (templateId: string) => void
  onSubmitParams: (params: Record<string, string>) => void
  onExecute: () => void
  onEditParams: () => void
  onCancel: () => void
}

export default function DetailPanel({
  state,
  templateDetail,
  paramValues,
  scriptPreview,
  onLockTemplate,
  onSubmitParams,
  onExecute,
  onEditParams,
  onCancel,
}: DetailPanelProps) {
  if (state === 'PARAM_COLLECT' && templateDetail) {
    return (
      <div className="flex flex-col h-full">
        {/* Task Banner */}
        <div
          className="px-[18px] py-3.5 border-b border-slate-200 flex items-center justify-between"
          style={{
            background: 'linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 100%)',
          }}
        >
          <div className="text-[12.5px] font-medium">
            当前任务 <strong className="text-emerald-600">{templateDetail.name}</strong>
            <span className="text-[11px] text-slate-400 ml-1.5 font-mono">
              {templateDetail.id}
            </span>
          </div>
          <button
            onClick={onCancel}
            className="text-[11px] font-medium px-2.5 py-[5px] rounded-md border border-red-100 text-red-600 hover:bg-red-50 transition-all"
          >
            放弃
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-[18px] py-4">
          <ParamForm
            params={templateDetail.params}
            values={paramValues}
            onSubmit={onSubmitParams}
            onCancel={onCancel}
          />
        </div>
      </div>
    )
  }

  if (state === 'SCRIPT_PREVIEW' && scriptPreview) {
    return (
      <div className="flex flex-col h-full">
        {/* Task Banner */}
        <div
          className="px-[18px] py-3.5 border-b border-slate-200 flex items-center justify-between"
          style={{
            background: 'linear-gradient(135deg, #eff6ff 0%, #eff6ff 100%)',
          }}
        >
          <div className="text-[12.5px] font-medium">
            脚本预览 <strong className="text-blue-600">{templateDetail?.name}</strong>
          </div>
          <button
            onClick={onCancel}
            className="text-[11px] font-medium px-2.5 py-[5px] rounded-md border border-red-100 text-red-600 hover:bg-red-50 transition-all"
          >
            放弃
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-[18px] py-4">
          <ScriptPreview
            script={scriptPreview}
            onExecute={onExecute}
            onEdit={onEditParams}
            onCancel={onCancel}
          />
        </div>
      </div>
    )
  }

  if (templateDetail) {
    // IDLE or INTENT_CONFIRM: show template info
    return (
      <div className="flex flex-col h-full">
        <div className="flex-1 overflow-y-auto px-[18px] py-4 space-y-4">
          {/* Header */}
          <div className="pb-4 border-b border-slate-100">
            <div className="flex items-center gap-1.5 mb-2">
              <span
                className={`text-[10.5px] font-semibold px-2 py-[3px] rounded-[5px] border ${
                  templateDetail.category === 'vector'
                    ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                    : templateDetail.category === 'raster'
                      ? 'bg-amber-50 text-amber-700 border-amber-200'
                      : 'bg-indigo-50 text-indigo-700 border-indigo-200'
                }`}
              >
                {templateDetail.category === 'vector'
                  ? '矢量'
                  : templateDetail.category === 'raster'
                    ? '栅格'
                    : templateDetail.category === 'database'
                      ? '数据库'
                      : '通用'}
              </span>
              <span className="text-[10.5px] text-slate-400 font-mono bg-slate-50 px-1.5 py-[2px] rounded">
                {templateDetail.tool_source || 'GDAL'}
              </span>
            </div>
            <h2 className="text-base font-semibold text-slate-900 tracking-tight">
              {templateDetail.name}
            </h2>
            <p className="text-xs text-slate-500 mt-1 leading-relaxed">
              {templateDetail.description}
            </p>
          </div>

          {/* Params preview */}
          {templateDetail.params.length > 0 && (
            <div>
              <h3 className="text-[10.5px] font-semibold text-slate-400 uppercase tracking-[0.8px] mb-3">
                参数
              </h3>
              <div className="space-y-2">
                {templateDetail.params.map((p) => (
                  <div
                    key={p.name}
                    className="flex items-center justify-between text-xs bg-slate-50 rounded-lg px-3 py-2"
                  >
                    <span className="font-medium text-slate-700">{p.name}</span>
                    <div className="flex items-center gap-2">
                      {p.required && (
                        <span className="text-[10px] text-red-500 font-semibold">*必填</span>
                      )}
                      <span className="text-[10px] text-slate-400 bg-white px-1.5 py-[1px] rounded">
                        {p.type}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {templateDetail.concepts.length > 0 && (
            <div>
              <h3 className="text-[10.5px] font-semibold text-slate-400 uppercase tracking-[0.8px] mb-3">
                概念
              </h3>
              <div className="space-y-2">
                {templateDetail.concepts.map((c, i) => (
                  <div key={i} className="text-xs leading-relaxed">
                    <span className="font-medium text-slate-700">{c.term}</span>
                    <span className="text-slate-500"> — {c.explanation}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {templateDetail.notes.length > 0 && (
            <div>
              <h3 className="text-[10.5px] font-semibold text-slate-400 uppercase tracking-[0.8px] mb-3">
                注意事项
              </h3>
              <div className="space-y-2">
                {templateDetail.notes.map((n, i) => (
                  <div key={i} className="flex gap-2.5 items-start text-xs leading-relaxed">
                    <span className="flex-shrink-0 mt-0.5">💡</span>
                    <span className="text-slate-600">{n}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {templateDetail.common_errors.length > 0 && (
            <div>
              <h3 className="text-[10.5px] font-semibold text-slate-400 uppercase tracking-[0.8px] mb-3">
                常见错误
              </h3>
              <div className="space-y-2">
                {templateDetail.common_errors.map((e, i) => (
                  <div
                    key={i}
                    className="rounded-lg bg-red-50 border border-red-100 p-3"
                  >
                    <p className="text-xs font-medium text-red-700">{e.error_text}</p>
                    <p className="text-xs text-red-600 mt-1 leading-relaxed">
                      修复: {e.fix}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {templateDetail.seealso.length > 0 && (
            <div>
              <h3 className="text-[10.5px] font-semibold text-slate-400 uppercase tracking-[0.8px] mb-3">
                相关模板
              </h3>
              <div className="flex flex-col gap-1">
                {templateDetail.seealso.map((s, i) => (
                  <div
                    key={i}
                    className="text-xs text-slate-500 px-2.5 py-1.5 rounded-lg hover:bg-slate-50 hover:text-blue-600 cursor-pointer transition-all flex items-center gap-2"
                  >
                    <span className="w-1.5 h-1.5 rounded-full bg-blue-400 flex-shrink-0" />
                    {s}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer action */}
        <div className="px-[18px] py-3.5 border-t border-slate-200 flex-shrink-0">
          <button
            onClick={() => onLockTemplate(templateDetail.id)}
            className="w-full h-10 rounded-xl bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-all shadow-[0_1px_4px_rgba(37,99,235,0.2)] flex items-center justify-center gap-1.5"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12" />
            </svg>
            使用此模板
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full items-center justify-center px-6 text-center">
      <div className="text-slate-300 mb-3">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <line x1="16" y1="13" x2="8" y2="13" />
          <line x1="16" y1="17" x2="8" y2="17" />
          <polyline points="10 9 9 9 8 9" />
        </svg>
      </div>
      <h2 className="text-sm font-semibold text-slate-500 mb-1">详情</h2>
      <p className="text-xs text-slate-400 leading-relaxed">
        从左栏选择一个模板查看详情，或在聊天区输入需求
      </p>
    </div>
  )
}
