import { useState } from 'react'
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

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {params.map((param) => (
        <div key={param.name}>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {param.name}
            {param.required && (
              <span className="text-red-500 ml-0.5">*</span>
            )}
          </label>
          {param.type === 'boolean' ? (
            <select
              value={values[param.name] || ''}
              onChange={(e) => handleChange(param.name, e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
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
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          ) : (
            <input
              type="text"
              value={values[param.name] || ''}
              onChange={(e) => handleChange(param.name, e.target.value)}
              placeholder={param.description}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          )}
          <p className="mt-1 text-xs text-gray-400">{param.description}</p>
        </div>
      ))}

      <div className="flex gap-2 pt-2">
        <button
          type="submit"
          className="flex-1 rounded-md bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700"
        >
          生成脚本
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
        >
          取消
        </button>
      </div>
    </form>
  )
}
