import { useState, useMemo } from 'react'
import type { ParamDef } from '../types'

interface ParamFormProps {
  params: ParamDef[]
  values: Record<string, string>
  onSubmit: (values: Record<string, string>) => void
  onCancel: () => void
}

export default function ParamForm({
  params,
  values: initialValues,
  onSubmit,
  onCancel,
}: ParamFormProps) {
  const [values, setValues] = useState<Record<string, string>>(() => {
    const v: Record<string, string> = {}
    for (const p of params) {
      v[p.name] = initialValues[p.name] ?? p.default ?? ''
    }
    return v
  })

  const handleChange = (name: string, value: string) => {
    setValues((prev) => ({ ...prev, [name]: value }))
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onSubmit(values)
  }

  // Calculate fill status
  const { filledCount, totalRequired } = useMemo(() => {
    const required = params.filter((p) => p.required)
    const filled = required.filter((p) => {
      const v = values[p.name]
      return v !== undefined && v !== ''
    })
    return { filledCount: filled.length, totalRequired: required.length }
  }, [params, values])

  const allOptional = totalRequired === 0

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* Fill status bar */}
      {!allOptional && (
        <div className="flex items-center justify-between mb-4">
          <div className="flex gap-1.5 flex-wrap">
            {params.map((p) => {
              const isFilled = p.required
                ? values[p.name] !== undefined && values[p.name] !== ''
                : true
              return (
                <span
                  key={p.name}
                  className="flex items-center gap-1 text-[11px] text-slate-500"
                >
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${
                      isFilled ? 'bg-emerald-500' : 'bg-amber-400'
                    }`}
                  />
                  {p.name}
                </span>
              )
            })}
          </div>
          <span className="text-[11px] text-emerald-600 font-semibold flex-shrink-0 ml-2">
            {filledCount}/{totalRequired} 已填写
          </span>
        </div>
      )}

      {params.map((param) => {
        const isFilled =
          values[param.name] !== undefined && values[param.name] !== ''
        const isRequired = param.required

        return (
          <div key={param.name}>
            <label className="flex items-center gap-1.5 text-[12.5px] font-medium text-slate-900 mb-1.5">
              {param.name}
              {isRequired && (
                <span className="text-red-500 text-[10px] font-semibold">
                  * 必填
                </span>
              )}
              <span className="text-[10px] text-slate-400 bg-slate-50 px-1.5 py-[1px] rounded ml-auto font-normal">
                {param.type}
              </span>
            </label>
            <p className="text-[11.5px] text-slate-400 mb-1.5 leading-relaxed">
              {param.description}
            </p>

            {param.type === 'boolean' ? (
              <select
                value={values[param.name] || ''}
                onChange={(e) => handleChange(param.name, e.target.value)}
                className="w-full h-9 border border-slate-200 rounded-lg px-3 text-[13px] bg-[#f8fafc] focus:border-blue-500 focus:bg-white focus:outline-none focus:ring-[3px] focus:ring-blue-500/8 transition-all"
              >
                <option value="">-- 选择 --</option>
                <option value="true">是</option>
                <option value="false">否</option>
              </select>
            ) : param.type === 'integer' ? (
              <input
                type="number"
                value={values[param.name] || ''}
                onChange={(e) => handleChange(param.name, e.target.value)}
                placeholder={param.description}
                className={`w-full h-9 border rounded-lg px-3 text-[13px] focus:outline-none focus:ring-[3px] focus:ring-blue-500/8 transition-all ${
                  isFilled
                    ? 'border-emerald-200 bg-emerald-50/50 text-emerald-800'
                    : 'border-slate-200 bg-[#f8fafc] focus:border-blue-500 focus:bg-white'
                }`}
              />
            ) : (
              <div className="relative">
                <input
                  type="text"
                  value={values[param.name] || ''}
                  onChange={(e) => handleChange(param.name, e.target.value)}
                  placeholder={param.description}
                  className={`w-full h-9 border rounded-lg px-3 text-[13px] focus:outline-none focus:ring-[3px] focus:ring-blue-500/8 transition-all ${
                    isFilled
                      ? 'border-emerald-200 bg-emerald-50/50 text-emerald-800'
                      : 'border-slate-200 bg-[#f8fafc] focus:border-blue-500 focus:bg-white'
                  }`}
                />
                {param.type === 'file_path' && (
                  <button
                    type="button"
                    className="absolute right-1.5 top-1/2 -translate-y-1/2 bg-white border border-slate-200 rounded-md px-2 py-[3px] text-[10.5px] text-slate-400 hover:border-blue-500 hover:text-blue-600 hover:bg-blue-50 transition-all"
                  >
                    浏览
                  </button>
                )}
              </div>
            )}

            {param.default && (
              <p className="text-[11px] text-slate-400 mt-1">
                默认: {param.default}
              </p>
            )}
          </div>
        )
      })}

      <div className="flex gap-2 pt-2">
        <button
          type="submit"
          className="flex-1 h-10 rounded-xl bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-all shadow-[0_1px_4px_rgba(37,99,235,0.2)] flex items-center justify-center gap-1.5"
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" />
            <polyline points="10 9 9 9 8 9" />
          </svg>
          生成脚本
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="h-10 rounded-xl border border-slate-200 px-4 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-all"
        >
          取消
        </button>
      </div>
    </form>
  )
}
