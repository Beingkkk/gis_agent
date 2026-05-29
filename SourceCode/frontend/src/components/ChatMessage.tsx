import { useState } from 'react'
import type { ChatMessage as ChatMessageType, CandidateTemplate } from '../types'

interface ChatMessageProps {
  message: ChatMessageType
  onSelectTemplate?: (templateId: string) => void
}

const MAX_VISIBLE_CARDS = 3

export default function ChatMessage({
  message,
  onSelectTemplate,
}: ChatMessageProps) {
  const isUser = message.role === 'user'
  const [showAllCards, setShowAllCards] = useState(false)

  if (message.type === 'cards' && message.meta?.candidates) {
    const candidates = message.meta.candidates as CandidateTemplate[]
    const visible = showAllCards ? candidates : candidates.slice(0, MAX_VISIBLE_CARDS)
    const hasMore = candidates.length > MAX_VISIBLE_CARDS

    return (
      <div className="flex gap-2.5 max-w-[88%] animate-[msgIn_0.3s_cubic-bezier(0.4,0,0.2,1)]">
        {/* Avatar */}
        <div
          className="w-7 h-7 rounded-lg flex items-center justify-center text-[11px] font-bold flex-shrink-0 mt-0.5"
          style={{
            background: 'linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%)',
            color: '#fff',
            boxShadow: '0 1px 4px rgba(37,99,235,0.2)',
          }}
        >
          AI
        </div>

        <div className="flex-1 min-w-0">
          {/* Bubble text */}
          {message.content && (
            <div className="bg-white px-4 py-3 rounded-2xl rounded-tl-sm border border-slate-200 text-[13.5px] leading-relaxed text-slate-900 shadow-sm mb-2">
              {message.content}
            </div>
          )}

          {/* Candidate cards — scrollable container to avoid pushing history away */}
          <div className={`space-y-2 ${hasMore && !showAllCards ? 'max-h-[280px] overflow-y-auto pr-1' : ''}`}>
            {visible.map((t) => (
              <button
                key={t.id}
                onClick={() => onSelectTemplate?.(t.id)}
                className="w-full text-left rounded-xl border border-slate-200 bg-white p-3.5 hover:border-blue-500 hover:bg-blue-50 transition-all duration-200 shadow-sm group"
              >
                <div className="text-[13.5px] font-semibold text-slate-900 group-hover:text-blue-600 transition-colors">
                  {t.name}
                </div>
                <div className="text-xs text-slate-500 mt-1 leading-relaxed">
                  {t.description}
                </div>
              </button>
            ))}
          </div>

          {/* Show more / less */}
          {hasMore && (
            <button
              onClick={() => setShowAllCards(!showAllCards)}
              className="mt-2 text-xs text-blue-600 hover:text-blue-700 font-medium"
            >
              {showAllCards
                ? '收起'
                : `还有 ${candidates.length - MAX_VISIBLE_CARDS} 个候选，点击展开`}
            </button>
          )}
        </div>
      </div>
    )
  }

  if (message.type === 'script') {
    return (
      <div className="flex gap-2.5 max-w-[92%] animate-[msgIn_0.3s_cubic-bezier(0.4,0,0.2,1)]">
        <div
          className="w-7 h-7 rounded-lg flex items-center justify-center text-[11px] font-bold flex-shrink-0 mt-0.5"
          style={{
            background: 'linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%)',
            color: '#fff',
            boxShadow: '0 1px 4px rgba(37,99,235,0.2)',
          }}
        >
          AI
        </div>
        <div className="flex-1 w-full">
          <div className="bg-[#0f172a] rounded-lg overflow-hidden">
            <div className="flex items-center justify-between px-3.5 py-2 border-b border-white/[0.06] bg-white/[0.02]">
              <span className="text-[11px] font-medium text-slate-400 font-mono">脚本预览</span>
            </div>
            <pre className="text-slate-200 p-3.5 text-xs font-mono leading-relaxed overflow-x-auto whitespace-pre-wrap">
              {message.content}
            </pre>
          </div>
        </div>
      </div>
    )
  }

  if (message.type === 'error') {
    return (
      <div className={`flex gap-2.5 max-w-[88%] animate-[msgIn_0.3s_cubic-bezier(0.4,0,0.2,1)] ${isUser ? 'self-end flex-row-reverse' : ''}`}>
        {!isUser && (
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center text-[11px] font-bold flex-shrink-0 mt-0.5"
            style={{
              background: 'linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%)',
              color: '#fff',
              boxShadow: '0 1px 4px rgba(37,99,235,0.2)',
            }}
          >
            AI
          </div>
        )}
        {isUser && (
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center text-[11px] font-bold flex-shrink-0 mt-0.5"
            style={{
              background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
              color: '#fff',
              boxShadow: '0 1px 4px rgba(16,185,129,0.2)',
            }}
          >
            我
          </div>
        )}
        <div className={`rounded-xl px-4 py-3 text-[13.5px] leading-relaxed shadow-sm ${
          isUser
            ? 'bg-blue-600 text-white rounded-tr-sm'
            : 'bg-red-50 border border-red-200 text-red-700 rounded-tl-sm'
        }`}>
          {message.content}
        </div>
      </div>
    )
  }

  // Default text message
  return (
    <div className={`flex gap-2.5 max-w-[88%] animate-[msgIn_0.3s_cubic-bezier(0.4,0,0.2,1)] ${isUser ? 'self-end flex-row-reverse' : ''}`}>
      {!isUser && (
        <div
          className="w-7 h-7 rounded-lg flex items-center justify-center text-[11px] font-bold flex-shrink-0 mt-0.5"
          style={{
            background: 'linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%)',
            color: '#fff',
            boxShadow: '0 1px 4px rgba(37,99,235,0.2)',
          }}
        >
          AI
        </div>
      )}
      {isUser && (
        <div
          className="w-7 h-7 rounded-lg flex items-center justify-center text-[11px] font-bold flex-shrink-0 mt-0.5"
          style={{
            background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
            color: '#fff',
            boxShadow: '0 1px 4px rgba(16,185,129,0.2)',
          }}
        >
          我
        </div>
      )}
      <div className={`rounded-xl px-4 py-3 text-[13.5px] leading-relaxed shadow-sm ${
        isUser
          ? 'bg-blue-600 text-white rounded-tr-sm border border-blue-600'
          : 'bg-white border border-slate-200 text-slate-900 rounded-tl-sm'
      }`}>
        <p className="whitespace-pre-wrap">{message.content}</p>
      </div>
    </div>
  )
}
