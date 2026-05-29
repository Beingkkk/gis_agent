interface ScriptPreviewProps {
  script: string
  onExecute: () => void
  onEdit: () => void
  onCancel: () => void
}

export default function ScriptPreview({
  script,
  onExecute,
  onEdit,
  onCancel,
}: ScriptPreviewProps) {
  const handleCopy = () => {
    navigator.clipboard.writeText(script)
  }

  return (
    <div className="space-y-4">
      <div className="relative">
        <div className="flex items-center justify-between bg-[#1e293b] text-slate-400 px-3.5 py-2 rounded-t-lg border-b border-white/[0.06]">
          <span className="text-[11px] font-medium font-mono">脚本预览</span>
          <button
            onClick={handleCopy}
            className="text-[11px] font-medium text-blue-400 hover:text-blue-300 transition-colors flex items-center gap-1"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
              <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
            </svg>
            复制
          </button>
        </div>
        <pre className="bg-[#0f172a] text-slate-200 p-3.5 text-xs font-mono rounded-b-lg overflow-x-auto whitespace-pre-wrap max-h-[400px] overflow-y-auto leading-relaxed">
          {script}
        </pre>
      </div>

      <div className="flex gap-2 pt-2">
        <button
          onClick={onExecute}
          className="flex-1 h-10 rounded-xl bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-700 transition-all shadow-[0_1px_4px_rgba(16,185,129,0.2)] flex items-center justify-center gap-1.5"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polygon points="5 3 19 12 5 21 5 3" />
          </svg>
          执行脚本
        </button>
        <button
          onClick={onEdit}
          className="h-10 rounded-xl border border-slate-200 px-4 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-all"
        >
          修改参数
        </button>
        <button
          onClick={onCancel}
          className="h-10 rounded-xl border border-red-200 px-4 text-sm font-medium text-red-600 hover:bg-red-50 transition-all"
        >
          取消
        </button>
      </div>
    </div>
  )
}
