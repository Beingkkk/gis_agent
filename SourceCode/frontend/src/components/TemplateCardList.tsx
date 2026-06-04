import type { TemplateDef } from '../types'

interface TemplateCardListProps {
  templates: TemplateDef[]
  searchQuery?: string
  selectedId?: string | null
  onSelect: (template: TemplateDef) => void
}

const CATEGORY_LABELS: Record<string, string> = {
  vector: '矢量',
  raster: '栅格',
  general: '通用',
  database: '数据库',
}

const CATEGORY_STYLES: Record<
  string,
  { bg: string; text: string; border: string; badgeBg: string }
> = {
  vector: {
    bg: 'bg-emerald-50',
    text: 'text-emerald-700',
    border: 'border-emerald-200',
    badgeBg: 'bg-emerald-100',
  },
  raster: {
    bg: 'bg-amber-50',
    text: 'text-amber-700',
    border: 'border-amber-200',
    badgeBg: 'bg-amber-100',
  },
  database: {
    bg: 'bg-purple-50',
    text: 'text-purple-700',
    border: 'border-purple-200',
    badgeBg: 'bg-purple-100',
  },
  general: {
    bg: 'bg-indigo-50',
    text: 'text-indigo-700',
    border: 'border-indigo-200',
    badgeBg: 'bg-indigo-100',
  },
}

/**
 * Highlight matching text in search results.
 */
function HighlightText({
  text,
  query,
}: {
  text: string
  query: string
}) {
  if (!query.trim()) return <>{text}</>
  const q = query.trim().toLowerCase()
  const parts: (string | JSX.Element)[] = []
  let lastIndex = 0
  const lowerText = text.toLowerCase()
  let index = lowerText.indexOf(q, lastIndex)
  while (index !== -1) {
    if (index > lastIndex) {
      parts.push(text.slice(lastIndex, index))
    }
    parts.push(
      <mark
        key={index}
        className="bg-yellow-200 text-yellow-900 rounded px-[1px]"
      >
        {text.slice(index, index + q.length)}
      </mark>,
    )
    lastIndex = index + q.length
    index = lowerText.indexOf(q, lastIndex)
  }
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex))
  }
  return <>{parts}</>
}

/**
 * TemplateCardList: 纯展示组件，以网格卡片形式展示模板。
 *
 * 职责：接收已过滤的模板列表，以 2 列网格渲染卡片。
 * 搜索高亮、选中状态、点击回调由上层控制。
 */
export default function TemplateCardList({
  templates,
  searchQuery = '',
  selectedId,
  onSelect,
}: TemplateCardListProps) {
  if (templates.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center px-6">
        <svg
          className="w-10 h-10 text-slate-300 mb-3"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={1.5}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
          />
        </svg>
        <p className="text-sm text-slate-400">未找到匹配的模板</p>
        {searchQuery && (
          <p className="text-xs text-slate-300 mt-1">
            尝试搜索关键词如 &quot;shp&quot;、&quot;geojson&quot;、&quot;转换&quot;
          </p>
        )}
      </div>
    )
  }

  return (
    <div className="grid grid-cols-2 gap-3 p-3">
      {templates.map((template) => {
        const cat = template.category || 'general'
        const styles = CATEGORY_STYLES[cat] || CATEGORY_STYLES.general
        const isSelected = selectedId === template.id

        return (
          <button
            key={template.id}
            onClick={() => onSelect(template)}
            className={`text-left rounded-xl border p-4 transition-all duration-200 relative overflow-hidden group ${
              isSelected
                ? 'border-blue-500 bg-blue-50 shadow-[0_0_0_3px_rgba(37,99,235,0.06)]'
                : 'border-slate-200 bg-white hover:border-slate-300 hover:shadow-md'
            }`}
          >
            {/* Category badge - top right */}
            <span
              className={`absolute top-2.5 right-2.5 text-2xs px-1.5 py-[2px] rounded border font-semibold ${styles.bg} ${styles.text} ${styles.border}`}
            >
              {CATEGORY_LABELS[cat] || cat}
            </span>

            {/* Selected indicator */}
            {isSelected && (
              <span className="absolute top-2.5 left-2.5 w-4 h-4 rounded-full bg-blue-500 flex items-center justify-center z-10">
                <svg
                  width="10"
                  height="10"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="white"
                  strokeWidth="3"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              </span>
            )}

            {/* Template ID */}
            <div className="mb-1.5 pr-16">
              <span className="text-2xs text-slate-400 font-mono bg-slate-50 px-1.5 py-[1px] rounded">
                <HighlightText text={template.id} query={searchQuery} />
              </span>
            </div>

            {/* Name */}
            <h3
              className={`text-base font-bold leading-tight mb-1.5 pr-2 ${
                isSelected ? 'text-blue-700' : 'text-slate-900 group-hover:text-blue-600'
              } transition-colors`}
            >
              <HighlightText text={template.name} query={searchQuery} />
            </h3>

            {/* Description */}
            <p className="text-xs text-slate-500 leading-relaxed line-clamp-2 mb-2">
              <HighlightText text={template.description} query={searchQuery} />
            </p>

            {/* Keywords */}
            {template.keywords && template.keywords.length > 0 && (
              <div className="flex gap-1 flex-wrap">
                {template.keywords.slice(0, 3).map((kw) => (
                  <span
                    key={kw}
                    className={`text-2xs px-1.5 py-[1px] rounded border ${
                      searchQuery.trim() &&
                      kw.toLowerCase().includes(searchQuery.trim().toLowerCase())
                        ? 'bg-yellow-100 border-yellow-300 text-yellow-700'
                        : 'bg-slate-50 border-slate-100 text-slate-400'
                    }`}
                  >
                    {kw}
                  </span>
                ))}
                {template.keywords.length > 3 && (
                  <span className="text-2xs px-1 py-[1px] text-slate-300">
                    +{template.keywords.length - 3}
                  </span>
                )}
              </div>
            )}

            {/* Tool source */}
            {template.tool_source && (
              <div className="mt-1.5">
                <span className="text-2xs px-1.5 py-[2px] bg-slate-50 text-slate-400 rounded">
                  {template.tool_source}
                </span>
              </div>
            )}
          </button>
        )
      })}
    </div>
  )
}
