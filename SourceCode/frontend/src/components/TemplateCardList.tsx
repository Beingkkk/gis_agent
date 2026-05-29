import { useState, useMemo } from 'react'
import type { TemplateDef } from '../types'

interface TemplateCardListProps {
  templates: TemplateDef[]
  selectedId: string | null
  onSelect: (template: TemplateDef) => void
}

const CATEGORY_LABELS: Record<string, string> = {
  vector: '矢量',
  raster: '栅格',
  general: '通用',
  database: '数据库',
}

const CATEGORY_STYLES: Record<string, { bg: string; text: string; border: string; bar: string }> = {
  vector: {
    bg: 'bg-emerald-50',
    text: 'text-emerald-700',
    border: 'border-emerald-200',
    bar: 'bg-emerald-500',
  },
  raster: {
    bg: 'bg-amber-50',
    text: 'text-amber-700',
    border: 'border-amber-200',
    bar: 'bg-amber-500',
  },
  database: {
    bg: 'bg-purple-50',
    text: 'text-purple-700',
    border: 'border-purple-200',
    bar: 'bg-purple-500',
  },
  general: {
    bg: 'bg-indigo-50',
    text: 'text-indigo-700',
    border: 'border-indigo-200',
    bar: 'bg-indigo-500',
  },
}

const TAG_FILTERS = [
  { key: 'all', label: '全部' },
  { key: 'vector', label: '矢量' },
  { key: 'raster', label: '栅格' },
  { key: 'general', label: '通用' },
]

const TAG_ACTIVE_STYLES: Record<string, string> = {
  all: 'bg-blue-50 text-blue-600 border-blue-200',
  vector: 'bg-emerald-50 text-emerald-600 border-emerald-200',
  raster: 'bg-amber-50 text-amber-600 border-amber-200',
  general: 'bg-indigo-50 text-indigo-600 border-indigo-200',
}

export default function TemplateCardList({
  templates,
  selectedId,
  onSelect,
}: TemplateCardListProps) {
  const [search, setSearch] = useState('')
  const [activeTag, setActiveTag] = useState('all')

  const filtered = useMemo(() => {
    let list = templates
    if (activeTag !== 'all') {
      list = list.filter((t) => t.category === activeTag)
    }
    if (search.trim()) {
      const q = search.trim().toLowerCase()
      list = list.filter(
        (t) =>
          t.name.toLowerCase().includes(q) ||
          t.id.toLowerCase().includes(q) ||
          (t.description || '').toLowerCase().includes(q)
      )
    }
    return list
  }, [templates, activeTag, search])

  // Group by category
  const byCategory = useMemo(() => {
    const groups: Record<string, TemplateDef[]> = {}
    for (const t of filtered) {
      const cat = t.category || 'general'
      groups[cat] = groups[cat] || []
      groups[cat].push(t)
    }
    return groups
  }, [filtered])

  const categories = Object.keys(byCategory).sort()

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 pt-5 pb-3 flex-shrink-0">
        <h2 className="text-[15px] font-semibold text-slate-900 tracking-tight">模板库</h2>
        <p className="text-xs text-slate-400 mt-0.5">选择模板开始数据处理任务</p>
      </div>

      {/* Search */}
      <div className="px-4 pb-2.5 flex-shrink-0">
        <div className="relative">
          <svg
            className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            type="text"
            placeholder="搜索模板..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full h-9 border border-slate-200 rounded-lg pl-8 pr-3 text-[13px] bg-[#f8fafc] focus:border-blue-500 focus:bg-white focus:outline-none focus:ring-[3px] focus:ring-blue-500/8 transition-all"
          />
        </div>
      </div>

      {/* Tag filters */}
      <div className="px-4 pb-3 flex gap-1.5 flex-wrap flex-shrink-0">
        {TAG_FILTERS.map((tag) => (
          <button
            key={tag.key}
            onClick={() => setActiveTag(tag.key)}
            className={`text-[11px] font-medium px-2.5 py-1 rounded-md border transition-all ${
              activeTag === tag.key
                ? TAG_ACTIVE_STYLES[tag.key]
                : 'bg-slate-50 text-slate-500 border-transparent hover:bg-slate-100'
            }`}
          >
            {tag.label}
          </button>
        ))}
      </div>

      {/* Card list */}
      <div className="flex-1 overflow-y-auto px-3 pb-2 min-h-0">
        {categories.length === 0 && (
          <div className="text-center text-slate-400 text-sm py-8">未找到匹配的模板</div>
        )}
        {categories.map((cat) => (
          <div key={cat} className="mb-4">
            <h3 className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2 px-1">
              {CATEGORY_LABELS[cat] || cat}
            </h3>
            <div className="space-y-2">
              {byCategory[cat].map((template) => {
                const styles = CATEGORY_STYLES[cat] || CATEGORY_STYLES.general
                const isSelected = selectedId === template.id

                return (
                  <button
                    key={template.id}
                    onClick={() => onSelect(template)}
                    className={`w-full text-left rounded-xl border p-3.5 transition-all duration-200 relative overflow-hidden group ${
                      isSelected
                        ? 'border-blue-500 bg-blue-50 shadow-[0_0_0_3px_rgba(37,99,235,0.06),0_4px_12px_rgba(0,0,0,0.06)]'
                        : 'border-slate-200 bg-white hover:-translate-y-0.5 hover:shadow-md hover:border-slate-300'
                    }`}
                  >
                    {/* Left color bar */}
                    <span
                      className={`absolute left-0 top-3 bottom-3 w-[3px] rounded-r-[3px] transition-opacity duration-150 ${
                        isSelected ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
                      } ${styles.bar}`}
                    />

                    {/* Title row: name + category badge */}
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[13.5px] font-semibold text-slate-900 group-hover:text-blue-600 transition-colors">
                        {template.name}
                      </span>
                      <span
                        className={`text-[10.5px] px-1.5 py-[3px] rounded-[5px] border font-semibold tracking-tight flex-shrink-0 ml-2 ${styles.bg} ${styles.text} ${styles.border}`}
                      >
                        {CATEGORY_LABELS[cat] || cat}
                      </span>
                    </div>

                    {/* Template ID (command) row */}
                    <div className="flex items-center gap-1 mb-1.5">
                      <span className="text-[10.5px] text-slate-400 font-mono bg-slate-50 px-1.5 py-[1px] rounded">
                        {template.id}
                      </span>
                    </div>

                    <p className="text-xs text-slate-500 leading-relaxed line-clamp-2">
                      {template.description}
                    </p>
                    {template.tool_source && (
                      <div className="flex gap-1.5 mt-2 flex-wrap">
                        <span className="text-[10.5px] px-1.5 py-[2px] bg-slate-50 text-slate-400 rounded">
                          {template.tool_source}
                        </span>
                        {template.tags?.slice(0, 2).map((tag) => (
                          <span
                            key={tag}
                            className="text-[10.5px] px-1.5 py-[2px] bg-slate-50 text-slate-400 rounded"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    )}
                  </button>
                )
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="px-3 py-3 border-t border-slate-200 flex-shrink-0">
        <button
          className="w-full h-9 border border-dashed border-slate-200 rounded-lg bg-slate-50 text-slate-500 text-[13px] font-medium flex items-center justify-center gap-1.5 hover:border-blue-500 hover:text-blue-600 hover:bg-blue-50 transition-all"
          onClick={() => {
            window.location.href = '/generator'
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          新建模板
        </button>
      </div>
    </div>
  )
}
