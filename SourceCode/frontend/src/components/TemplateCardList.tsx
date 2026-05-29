import type { TemplateDef } from '../types'

interface TemplateCardListProps {
  templates: TemplateDef[]
  selectedId: string | null
  onSelect: (template: TemplateDef) => void
}

function categoryColor(category: string): string {
  switch (category) {
    case 'vector':
      return 'bg-green-50 text-green-700 border-green-200'
    case 'raster':
      return 'bg-amber-50 text-amber-700 border-amber-200'
    case 'database':
      return 'bg-purple-50 text-purple-700 border-purple-200'
    default:
      return 'bg-gray-50 text-gray-600 border-gray-200'
  }
}

export default function TemplateCardList({
  templates,
  selectedId,
  onSelect,
}: TemplateCardListProps) {
  // Group by category
  const byCategory: Record<string, TemplateDef[]> = {}
  for (const t of templates) {
    const cat = t.category || 'general'
    byCategory[cat] = byCategory[cat] || []
    byCategory[cat].push(t)
  }

  const categories = Object.keys(byCategory).sort()

  return (
    <div className="space-y-4">
      {categories.map((cat) => (
        <div key={cat}>
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2 px-1">
            {cat}
          </h3>
          <div className="space-y-2">
            {byCategory[cat].map((template) => (
              <button
                key={template.id}
                onClick={() => onSelect(template)}
                className={`w-full text-left rounded-lg border p-3 transition-colors ${
                  selectedId === template.id
                    ? 'border-primary-500 bg-primary-50 ring-1 ring-primary-500'
                    : 'border-gray-200 bg-white hover:border-gray-300 hover:bg-gray-50'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium text-gray-800">
                    {template.name}
                  </span>
                  <span
                    className={`text-[10px] px-1.5 py-0.5 rounded border ${categoryColor(
                      template.category
                    )}`}
                  >
                    {template.category}
                  </span>
                </div>
                <p className="text-xs text-gray-500 line-clamp-2">
                  {template.description}
                </p>
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
