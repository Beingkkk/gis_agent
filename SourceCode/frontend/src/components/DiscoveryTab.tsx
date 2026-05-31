/**
 * DiscoveryTab: 模板识别 TAB（DC-UX-10）
 *
 * 职责：模板搜索浏览 + LLM 意图匹配 + 候选模板确认
 * 特点：统一输入框（本地模板过滤 + 远程意图发送），网格卡片布局
 *
 * Design: DC-UX-10, DC-UX-02
 */

import { useState, useRef, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import TemplateCardList from './TemplateCardList'
import type { TemplateDef, CandidateTemplate, SessionState } from '../types'

interface DiscoveryTabProps {
  templates: TemplateDef[]
  selectedId: string | null
  candidates: CandidateTemplate[]
  state: SessionState
  isLoading: boolean
  onSelectTemplate: (template: TemplateDef) => void
  onSelectCandidate: (templateId: string) => void
  onSendIntent: (text: string) => void
}

const TAG_FILTERS = [
  { key: 'all', label: '全部' },
  { key: 'vector', label: '矢量' },
  { key: 'raster', label: '栅格' },
  { key: 'general', label: '通用' },
  { key: 'database', label: '数据库' },
]

const TAG_ACTIVE_STYLES: Record<string, string> = {
  all: 'bg-blue-50 text-blue-600 border-blue-200',
  vector: 'bg-emerald-50 text-emerald-600 border-emerald-200',
  raster: 'bg-amber-50 text-amber-600 border-amber-200',
  general: 'bg-indigo-50 text-indigo-600 border-indigo-200',
  database: 'bg-purple-50 text-purple-600 border-purple-200',
}

/** 加载动画组件 */
function LoadingOverlay({ message }: { message: string }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center">
      <div className="w-10 h-10 border-3 border-slate-200 border-t-blue-500 rounded-full animate-spin mb-4" />
      <p className="text-sm font-medium text-slate-600">{message}</p>
      <p className="text-xs text-slate-400 mt-1">请稍候...</p>
    </div>
  )
}

/** 候选模板卡片（INTENT_CONFIRM 状态） */
function CandidateCard({
  candidate,
  index,
  onClick,
}: {
  candidate: CandidateTemplate
  index: number
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className="text-left rounded-xl border border-slate-200 bg-white p-4 hover:border-blue-500 hover:bg-blue-50 transition-all duration-200 shadow-sm group"
    >
      <div className="flex items-start gap-3">
        <span className="w-8 h-8 rounded-lg bg-blue-100 text-blue-600 flex items-center justify-center text-xs font-bold flex-shrink-0 mt-0.5">
          {index + 1}
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-[14px] font-semibold text-slate-900 group-hover:text-blue-600 transition-colors">
            {candidate.name}
          </div>
          <div className="text-xs text-slate-500 mt-1 leading-relaxed">
            {candidate.description}
          </div>
          <div className="mt-2 flex items-center gap-1 text-[11px] text-blue-500 font-medium">
            <span>点击选择此模板</span>
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </div>
        </div>
      </div>
    </button>
  )
}

export default function DiscoveryTab({
  templates,
  selectedId,
  candidates,
  state,
  isLoading,
  onSelectTemplate,
  onSelectCandidate,
  onSendIntent,
}: DiscoveryTabProps) {
  const navigate = useNavigate()
  const [searchQuery, setSearchQuery] = useState('')
  const [activeTag, setActiveTag] = useState('all')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current
    if (el) {
      el.style.height = 'auto'
      el.style.height = Math.min(el.scrollHeight, 120) + 'px'
    }
  }, [searchQuery])

  // 本地过滤模板
  const filteredTemplates = useMemo(() => {
    let list = templates
    if (activeTag !== 'all') {
      list = list.filter((t) => t.category === activeTag)
    }
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase()
      list = list.filter(
        (t) =>
          t.name.toLowerCase().includes(q) ||
          t.id.toLowerCase().includes(q) ||
          (t.description || '').toLowerCase().includes(q) ||
          (t.keywords || []).some((kw) => kw.toLowerCase().includes(q)),
      )
    }
    return list
  }, [templates, activeTag, searchQuery])

  // 分类计数（基于当前搜索）
  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    const q = searchQuery.trim().toLowerCase()
    const source = q
      ? templates.filter(
          (t) =>
            t.name.toLowerCase().includes(q) ||
            t.id.toLowerCase().includes(q) ||
            (t.description || '').toLowerCase().includes(q) ||
            (t.keywords || []).some((kw) => kw.toLowerCase().includes(q)),
        )
      : templates
    for (const t of source) {
      const cat = t.category || 'general'
      counts[cat] = (counts[cat] || 0) + 1
    }
    counts['all'] = Object.values(counts).reduce((a, b) => a + b, 0)
    return counts
  }, [templates, searchQuery])

  // 当前显示模式
  const showCandidates = state === 'INTENT_CONFIRM' && candidates.length > 0
  const isSearching = isLoading && (state === 'IDLE' || state === 'INTENT_CONFIRM')

  const handleSend = () => {
    const text = searchQuery.trim()
    if (!text || isLoading) return
    onSendIntent(text)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleClear = () => {
    setSearchQuery('')
    setActiveTag('all')
  }

  return (
    <div className="flex flex-col h-full">
      {/* ─── 模板区域 ─── */}
      <div className="flex-1 overflow-hidden flex flex-col min-h-0">
        {/* 加载状态 */}
        {isSearching && <LoadingOverlay message="正在分析您的需求..." />}

        {/* 候选结果模式 */}
        {showCandidates && !isSearching && (
          <div className="flex-1 overflow-y-auto">
            {/* 候选结果标题 */}
            <div className="px-5 pt-5 pb-3">
              <h2 className="text-[15px] font-semibold text-slate-900 tracking-tight"
              >
                匹配到 {candidates.length} 个候选模板
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                请点击选择最符合需求的模板
              </p>
            </div>
            {/* 候选卡片网格 */}
            <div className="grid grid-cols-1 gap-3 px-3 pb-4">
              {candidates.map((c, idx) => (
                <CandidateCard
                  key={c.id}
                  candidate={c}
                  index={idx}
                  onClick={() => onSelectCandidate(c.id)}
                />
              ))}
            </div>
          </div>
        )}

        {/* 浏览 / 匹配模式 */}
        {!isSearching && !showCandidates && (
          <>
            {/* 头部：标题 + 计数 */}
            <div className="px-4 pt-4 pb-2 flex-shrink-0 flex items-center justify-between"
            >
              <div>
                <h2 className="text-[15px] font-semibold text-slate-900 tracking-tight"
                >
                  模板库
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  {searchQuery.trim()
                    ? `找到 ${filteredTemplates.length} 个结果`
                    : '选择模板开始数据处理任务'}
                </p>
              </div>
              <span className="text-[11px] font-medium text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full"
              >
                {filteredTemplates.length}
              </span>
            </div>

            {/* 状态提示：PARAM_COLLECT / 未匹配 */}
            {state === 'PARAM_COLLECT' && (
              <div className="mx-4 mb-2 px-3 py-2 rounded-lg bg-emerald-50 border border-emerald-100 flex-shrink-0"
              >
                <p className="text-xs text-emerald-700 font-medium"
                >
                  ✓ 已确认模板，请填写参数
                </p>
              </div>
            )}
            {state === 'INTENT_CONFIRM' && candidates.length === 0 && (
              <div className="mx-4 mb-2 px-3 py-2 rounded-lg bg-amber-50 border border-amber-100 flex-shrink-0"
              >
                <p className="text-xs text-amber-700 font-medium"
                >
                  未找到匹配的模板，请尝试其他描述或从下方手动选择
                </p>
              </div>
            )}

            {/* 分类标签过滤器 */}
            <div className="px-4 pb-2.5 flex gap-1.5 flex-wrap flex-shrink-0"
            >
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
                  <span
                    className={`ml-1 ${activeTag === tag.key ? 'opacity-80' : 'text-slate-400'}`}
                  >
                    {categoryCounts[tag.key] || 0}
                  </span>
                </button>
              ))}
            </div>

            {/* 模板网格 */}
            <div className="flex-1 overflow-y-auto min-h-0">
              <TemplateCardList
                templates={filteredTemplates}
                searchQuery={searchQuery}
                selectedId={selectedId}
                onSelect={onSelectTemplate}
              />
            </div>

            {/* 新建模板按钮 */}
            <div className="px-3 py-2.5 border-t border-slate-200 flex-shrink-0"
            >
              <button
                className="w-full h-9 border border-dashed border-slate-200 rounded-lg bg-slate-50 text-slate-500 text-[13px] font-medium flex items-center justify-center gap-1.5 hover:border-blue-500 hover:text-blue-600 hover:bg-blue-50 transition-all"
                onClick={() => navigate('/generator')}
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
                >
                  <line x1="12" y1="5" x2="12" y2="19" />
                  <line x1="5" y1="12" x2="19" y2="12" />
                </svg>
                新建模板
              </button>
            </div>
          </>
        )}
      </div>

      {/* ─── 底部统一输入框 ─── */}
      <div className="border-t border-slate-200 bg-white px-5 py-3 flex-shrink-0"
      >
        <div
          className={`flex gap-2 items-end bg-white border rounded-2xl px-3 py-1.5 shadow-sm transition-all ${
            isLoading
              ? 'border-slate-200 opacity-70'
              : 'border-slate-200 focus-within:border-blue-500 focus-within:shadow-[0_0_0_3px_rgba(37,99,235,0.08),0_1px_3px_rgba(0,0,0,0.06)]'
          }`}
        >
          <textarea
            ref={textareaRef}
            rows={1}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              state === 'PARAM_COLLECT'
                ? '描述更多需求，或按 Enter 重新匹配...'
                : '描述需求，如"shp转geojson"，实时过滤模板...'
            }
            disabled={isLoading}
            className="flex-1 border-none outline-none resize-none text-sm leading-relaxed py-2 bg-transparent text-slate-900 min-h-[22px] max-h-[120px] disabled:opacity-50"
          />

          {/* 清空按钮 */}
          {searchQuery && (
            <button
              onClick={handleClear}
              className="w-7 h-7 rounded-lg flex items-center justify-center text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-all flex-shrink-0"
              title="清空"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          )}

          {/* 发送按钮 */}
          <button
            onClick={handleSend}
            disabled={isLoading || !searchQuery.trim()}
            className="w-8 h-8 rounded-[10px] bg-blue-600 text-white flex items-center justify-center flex-shrink-0 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-[0_1px_4px_rgba(37,99,235,0.2)]"
          >
            {isLoading ? (
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            )}
          </button>
        </div>
        <p className="text-[11px] text-slate-400 mt-2 text-center"
        >
          {searchQuery.trim()
            ? '按 Enter 发送意图匹配，实时过滤中...'
            : '输入内容实时过滤模板，按 Enter 发送意图匹配'}
        </p>
      </div>
    </div>
  )
}
