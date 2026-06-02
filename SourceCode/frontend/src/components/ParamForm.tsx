import { useState, useMemo, useCallback } from 'react'
import { selectFile, selectDirectory } from '../electron-api'
import { groupParams, sortGroups } from './paramGroups'
import type { ParamDef } from '../types'

interface ParamFormProps {
  params: ParamDef[]
  values: Record<string, string>
  workspace?: string | null
  onSubmit: (values: Record<string, string>) => void
  onCancel?: () => void
  /** 只读模式：禁用输入、隐藏底部操作按钮 */
  readOnly?: boolean
}

// ═══════════════════════════════════════════════════════════════════════════
// 子组件
// ═══════════════════════════════════════════════════════════════════════════

/** 彩色类型标签 */
function TypeTag({ type }: { type: string }) {
  const config = useMemo(() => {
    switch (type) {
      case 'file_path':
      case 'folder_path':
        return { cls: 'bg-amber-50 text-amber-700', label: '文件' }
      case 'enum':
      case 'format':
        return { cls: 'bg-violet-50 text-violet-700', label: '枚举' }
      case 'crs':
        return { cls: 'bg-pink-50 text-pink-700', label: '坐标系' }
      case 'boolean':
        return { cls: 'bg-emerald-50 text-emerald-700', label: '布尔' }
      case 'integer':
      case 'float':
        return { cls: 'bg-blue-50 text-blue-700', label: '数值' }
      case 'text':
        return { cls: 'bg-slate-100 text-slate-600', label: '文本' }
      default:
        return { cls: 'bg-slate-100 text-slate-600', label: type }
    }
  }, [type])

  return (
    <span
      className={`inline-block text-[9.5px] font-medium px-[5px] py-[1px] rounded ${config.cls}`}
    >
      {config.label}
    </span>
  )
}

/** 描述 Tooltip（hover 在 ? 图标上显示） */
function InfoTooltip({ description }: { description: string }) {
  if (!description) return null
  return (
    <span className="group relative inline-flex items-center cursor-help">
      <svg
        width="13"
        height="13"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="text-slate-300 group-hover:text-blue-400 transition-colors"
      >
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="16" x2="12" y2="12" />
        <line x1="12" y1="8" x2="12.01" y2="8" />
      </svg>
      <span className="absolute left-full top-1/2 -translate-y-1/2 ml-2 z-50
        w-[240px] px-3 py-2 rounded-lg bg-slate-800 text-slate-200
        text-[11px] leading-relaxed shadow-lg
        opacity-0 invisible group-hover:opacity-100 group-hover:visible
        transition-all duration-150 pointer-events-none"
      >
        {description}
        <span className="absolute right-full top-1/2 -translate-y-1/2
          border-[5px] border-transparent border-r-slate-800" />
      </span>
    </span>
  )
}

/** 进度条 */
function ProgressBar({
  filled,
  total,
}: {
  filled: number
  total: number
}) {
  const pct = total > 0 ? Math.round((filled / total) * 100) : 100
  return (
    <div className="flex items-center gap-2.5">
      <div className="flex-1 h-[5px] bg-slate-100 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full bg-gradient-to-r from-blue-500 to-blue-400
            transition-all duration-500 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[10.5px] text-slate-400 font-medium whitespace-nowrap">
        {filled} / {total} 已填写
      </span>
    </div>
  )
}

/** 单行参数渲染（水平布局：label 左 / input 右） */
function ParamRow({
  param,
  value,
  onChange,
  onBrowse,
  readOnly,
}: {
  param: ParamDef
  value: string
  onChange: (name: string, v: string) => void
  onBrowse: (name: string, isDir: boolean) => void
  readOnly?: boolean
}) {
  const isFilled = value !== ''
  const inputBase = `w-full h-8 border rounded-lg px-2.5 text-[12.5px]
    transition-all focus:outline-none focus:ring-[3px] focus:ring-blue-500/8`
  const inputFilled = readOnly
    ? `border-slate-100 bg-slate-50 text-slate-700 cursor-default`
    : `border-emerald-200 bg-emerald-50/60 text-emerald-800`
  const inputEmpty = readOnly
    ? `border-slate-100 bg-slate-50 text-slate-400 cursor-default`
    : `border-slate-200 bg-[#f8fafc] focus:border-blue-500 focus:bg-white`
  const inputCls = `${inputBase} ${isFilled ? inputFilled : inputEmpty}`

  const renderInput = () => {
    const common = {
      value: value || '',
      className: inputCls,
      readOnly,
      disabled: readOnly,
    }

    switch (param.type) {
      case 'boolean':
        return (
          <select
            {...common}
            onChange={(e) => onChange(param.name, e.target.value)}
          >
            <option value="">— 默认 —</option>
            <option value="true">是</option>
            <option value="false">否</option>
          </select>
        )

      case 'enum':
      case 'format':
        return (
          <select
            {...common}
            onChange={(e) => onChange(param.name, e.target.value)}
          >
            <option value="">— 选择 —</option>
            {param.options?.map((opt) => (
              <option key={opt} value={opt}>{opt}</option>
            ))}
          </select>
        )

      case 'text':
        return (
          <textarea
            {...common}
            rows={2}
            placeholder={param.description}
            onChange={(e) => onChange(param.name, e.target.value)}
            className={`${inputCls} py-1.5 resize-y font-sans`}
          />
        )

      case 'integer':
        return (
          <input
            type="number"
            step="1"
            {...common}
            placeholder={param.description || '整数'}
            onChange={(e) => onChange(param.name, e.target.value)}
          />
        )

      case 'float':
        return (
          <input
            type="number"
            step="any"
            {...common}
            placeholder={param.description || '数值'}
            onChange={(e) => onChange(param.name, e.target.value)}
          />
        )

      case 'file_path':
      case 'folder_path':
        return (
          <div className="flex gap-1.5">
            <input
              type="text"
              {...common}
              placeholder={param.description || '选择路径…'}
              onChange={(e) => !readOnly && onChange(param.name, e.target.value)}
              className={`${inputCls} flex-1`}
            />
            {!readOnly && (
              <button
                type="button"
                onClick={() => onBrowse(param.name, param.type === 'folder_path')}
                className="h-8 px-2.5 border border-slate-200 rounded-lg
                  text-[11px] font-medium text-slate-500 bg-white
                  hover:bg-slate-50 hover:border-slate-300 transition-all
                  whitespace-nowrap flex-shrink-0"
              >
                浏览…
              </button>
            )}
          </div>
        )

      default:
        return (
          <input
            type="text"
            {...common}
            placeholder={param.description}
            onChange={(e) => onChange(param.name, e.target.value)}
          />
        )
    }
  }

  return (
    <div className="flex items-start gap-3 py-[7px] min-h-[40px]">
      {/* Label column */}
      <div className="w-[140px] flex-shrink-0 flex flex-col gap-[2px] pt-[5px]">
        <div className="flex items-center gap-1 text-[12px] font-medium text-slate-700"
        >
          <span className="truncate" title={param.name}>{param.name}</span>
          {param.required && (
            <span className="text-red-400 text-[11px]">*</span>
          )}
          <InfoTooltip description={param.description} />
        </div>
        <TypeTag type={param.type} />
      </div>

      {/* Input column */}
      <div className="flex-1 min-w-0 flex flex-col gap-[2px]">
        {renderInput()}
        {param.default && !isFilled && (
          <span className="text-[10.5px] text-slate-400 flex items-center gap-1"
          >
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth="2.5"
              strokeLinecap="round" strokeLinejoin="round"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="16" x2="12" y2="12" />
              <line x1="12" y1="8" x2="12.01" y2="8" />
            </svg>
            默认: {param.default}
          </span>
        )}
      </div>
    </div>
  )
}

/** 可折叠参数分组 */
function ParamSection({
  title,
  params,
  values,
  onChange,
  onBrowse,
  onToggleExpand,
  expanded,
  readOnly,
}: {
  title: string
  params: ParamDef[]
  values: Record<string, string>
  onChange: (name: string, v: string) => void
  onBrowse: (name: string, isDir: boolean) => void
  onToggleExpand: () => void
  expanded: boolean
  readOnly?: boolean
}) {
  const filledCount = params.filter(
    (p) => values[p.name] !== undefined && values[p.name] !== '',
  ).length

  const sectionIcons: Record<string, string> = {
    '输入输出': 'M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12',
    '坐标系设置': 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z',
    '变换选项': 'M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15',
    '裁剪与范围': 'M4 4h16v16H4zM4 12h16M12 4v16',
    '高级选项': 'M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4',
  }

  const sectionColors: Record<string, string> = {
    '输入输出': 'bg-blue-50 text-blue-600',
    '坐标系设置': 'bg-pink-50 text-pink-600',
    '变换选项': 'bg-violet-50 text-violet-600',
    '裁剪与范围': 'bg-amber-50 text-amber-600',
    '高级选项': 'bg-slate-100 text-slate-500',
  }

  const iconPath = sectionIcons[title] || 'M4 6h16M4 12h16M4 18h16'
  const colorCls = sectionColors[title] || 'bg-slate-100 text-slate-500'

  return (
    <div className="border-b border-slate-100 last:border-b-0"
    >
      {/* Section header */}
      <button
        type="button"
        onClick={onToggleExpand}
        className="w-full flex items-center gap-2 px-5 py-2.5
          hover:bg-slate-50 transition-colors text-left"
      >
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={`text-slate-400 flex-shrink-0 transition-transform duration-200
            ${expanded ? 'rotate-90' : ''}`}
        >
          <polyline points="9 18 15 12 9 6" />
        </svg>

        <div className={`w-5 h-5 rounded-md flex items-center justify-center
          flex-shrink-0 ${colorCls}`}
        >
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2.5"
            strokeLinecap="round" strokeLinejoin="round"
          >
            <path d={iconPath} />
          </svg>
        </div>

        <span className="text-[12px] font-semibold text-slate-700 flex-1"
        >
          {title}
        </span>

        <span className="text-[10.5px] text-slate-400 font-medium
          bg-slate-50 px-[7px] py-[1px] rounded"
        >
          {filledCount} / {params.length}
        </span>
      </button>

      {/* Section body */}
      <div
        className={`overflow-hidden transition-all duration-200
          ${expanded ? 'max-h-[2000px] opacity-100' : 'max-h-0 opacity-0'}`}
      >
        <div className="px-5 pb-3"
        >
          {params.map((param, idx) => (
            <div key={param.name}
            >
              <ParamRow
                param={param}
                value={values[param.name] ?? ''}
                onChange={onChange}
                onBrowse={onBrowse}
                readOnly={readOnly}
              />
              {idx < params.length - 1 && (
                <div className="border-t border-slate-50" />
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// 主组件
// ═══════════════════════════════════════════════════════════════════════════

export default function ParamForm({
  params,
  values: initialValues,
  workspace,
  onSubmit,
  onCancel,
  readOnly = false,
}: ParamFormProps) {
  const [values, setValues] = useState<Record<string, string>>(() => {
    const v: Record<string, string> = {}
    for (const p of params) {
      v[p.name] = initialValues[p.name] ?? p.default ?? ''
    }
    return v
  })

  const [expandedSections, setExpandedSections] = useState<
    Set<string>
  >(() => {
    // 默认展开含必填参数的分组
    const grouped = groupParams(params)
    const expanded = new Set<string>()
    for (const [groupName, groupParams_] of grouped) {
      if (groupParams_.some((p) => p.required)) {
        expanded.add(groupName)
      }
    }
    return expanded
  })

  const handleChange = useCallback((name: string, value: string) => {
    setValues((prev) => ({ ...prev, [name]: value }))
  }, [])

  const handleBrowse = useCallback(
    async (paramName: string, isDir: boolean) => {
      const path = isDir
        ? await selectDirectory({ defaultPath: workspace || undefined })
        : await selectFile({ defaultPath: workspace || undefined })
      if (path) {
        handleChange(paramName, path)
      }
    },
    [workspace, handleChange],
  )

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onSubmit(values)
  }

  const toggleSection = useCallback((name: string) => {
    setExpandedSections((prev) => {
      const next = new Set(prev)
      if (next.has(name)) {
        next.delete(name)
      } else {
        next.add(name)
      }
      return next
    })
  }, [])

  const expandAll = useCallback(() => {
    const grouped = groupParams(params)
    setExpandedSections(new Set(grouped.keys()))
  }, [params])

  const collapseAll = useCallback(() => {
    setExpandedSections(new Set())
  }, [])

  // 计算进度
  const { filledCount, totalCount } = useMemo(() => {
    const filled = params.filter(
      (p) => values[p.name] !== undefined && values[p.name] !== '',
    ).length
    return { filledCount: filled, totalCount: params.length }
  }, [params, values])

  // 分组并排序
  const sortedGroups = useMemo(() => {
    const grouped = groupParams(params)
    return sortGroups(grouped)
  }, [params])

  return (
    <form onSubmit={handleSubmit} className="flex flex-col h-full"
    >
      {/* Header: title + expand/collapse + progress */}
      <div className="px-5 pt-4 pb-3 border-b border-slate-100 flex-shrink-0"
      >
        <div className="flex items-center justify-between mb-2.5"
        >
          <span className="text-[13px] font-bold text-slate-800"
          >
            {readOnly ? '参数值' : '参数设置'}
          </span>
          {!readOnly && (
            <div className="flex gap-1"
            >
              <button
                type="button"
                onClick={collapseAll}
                className="text-[11px] px-2 py-[3px] rounded-md border border-slate-200
                  text-slate-500 hover:bg-slate-50 transition-all"
              >
                − 收起
              </button>
              <button
                type="button"
                onClick={expandAll}
                className="text-[11px] px-2 py-[3px] rounded-md border border-slate-200
                  text-slate-500 hover:bg-slate-50 transition-all"
              >
                + 展开
              </button>
            </div>
          )}
        </div>
        <ProgressBar filled={filledCount} total={totalCount} />
      </div>

      {/* Grouped params */}
      <div className="flex-1 overflow-y-auto"
      >
        {sortedGroups.map(([groupName, groupParams_]) => (
          <ParamSection
            key={groupName}
            title={groupName}
            params={groupParams_}
            values={values}
            onChange={handleChange}
            onBrowse={handleBrowse}
            onToggleExpand={() => toggleSection(groupName)}
            expanded={expandedSections.has(groupName)}
            readOnly={readOnly}
          />
        ))}
      </div>

      {/* Footer actions */}
      {!readOnly && (
        <div className="px-5 py-3 border-t border-slate-100 flex-shrink-0
          flex gap-2"
        >
          <button
            type="submit"
            className={`h-9 rounded-lg bg-blue-600 text-white
              text-[12.5px] font-semibold hover:bg-blue-700 transition-all
              shadow-[0_1px_3px_rgba(37,99,235,0.2)]
              flex items-center justify-center gap-1.5
              ${onCancel ? 'flex-1' : 'w-full'}`}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth="2.5"
              strokeLinecap="round" strokeLinejoin="round"
            >
              <polyline points="20 6 9 17 4 12" />
            </svg>
            确认参数
          </button>
          {onCancel && (
            <button
              type="button"
              onClick={onCancel}
              className="h-9 rounded-lg border border-slate-200 px-4
                text-[12.5px] font-medium text-slate-600
                hover:bg-slate-50 transition-all"
            >
              取消
            </button>
          )}
        </div>
      )}
    </form>
  )
}
