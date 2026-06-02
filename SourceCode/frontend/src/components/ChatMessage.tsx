import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
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

  if (message.type === 'timeline' && message.meta?.steps) {
    const steps = message.meta.steps as Array<{
      order: number
      template_name: string
      status: 'pending' | 'running' | 'done' | 'error'
    }>
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
          {message.content && (
            <div className="bg-white px-4 py-3 rounded-2xl rounded-tl-sm border border-slate-200 text-[13.5px] leading-relaxed text-slate-900 shadow-sm mb-2">
              {message.content}
            </div>
          )}
          <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
            <div className="flex items-center gap-1">
              {steps.map((step, i) => (
                <div key={step.order} className="flex items-center gap-1 flex-1">
                  <div className={`flex-1 h-2 rounded-full ${
                    step.status === 'done' ? 'bg-emerald-400' :
                    step.status === 'running' ? 'bg-blue-400' :
                    step.status === 'error' ? 'bg-red-400' :
                    'bg-slate-200'
                  }`} />
                  {i < steps.length - 1 && (
                    <div className={`w-3 h-px ${
                      step.status === 'done' ? 'bg-emerald-400' : 'bg-slate-200'
                    }`} />
                  )}
                </div>
              ))}
            </div>
            <div className="flex justify-between mt-2">
              {steps.map((step) => (
                <div key={step.order} className="flex-1 text-center">
                  <span className={`text-[11px] font-medium ${
                    step.status === 'done' ? 'text-emerald-600' :
                    step.status === 'running' ? 'text-blue-600' :
                    step.status === 'error' ? 'text-red-600' :
                    'text-slate-400'
                  }`}>
                    {step.template_name}
                  </span>
                </div>
              ))}
            </div>
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
        {isUser ? (
          <p className="whitespace-pre-wrap">{message.content}</p>
        ) : (
          <div className="markdown-body [&_p]:mb-2 [&_p:last-child]:mb-0 [&_h1]:text-base [&_h1]:font-bold [&_h1]:mb-2 [&_h2]:text-[14px] [&_h2]:font-bold [&_h2]:mb-2 [&_h3]:text-[13.5px] [&_h3]:font-bold [&_h3]:mb-1.5 [&_ul]:list-disc [&_ul]:pl-4 [&_ul]:mb-2 [&_ol]:list-decimal [&_ol]:pl-4 [&_ol]:mb-2 [&_li]:mb-1 [&_pre]:bg-slate-900 [&_pre]:text-slate-200 [&_pre]:p-3 [&_pre]:rounded-md [&_pre]:text-xs [&_pre]:font-mono [&_pre]:overflow-x-auto [&_pre]:my-2 [&_code]:bg-slate-100 [&_code]:text-slate-700 [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-xs [&_code]:font-mono [&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_pre_code]:text-inherit [&_a]:text-blue-600 [&_a]:underline [&_table]:w-full [&_table]:border-collapse [&_table]:my-2 [&_th]:border [&_th]:border-slate-200 [&_th]:px-2 [&_th]:py-1 [&_th]:text-left [&_th]:font-semibold [&_th]:bg-slate-50 [&_td]:border [&_td]:border-slate-200 [&_td]:px-2 [&_td]:py-1 [&_hr]:my-3 [&_hr]:border-slate-200 [&_blockquote]:border-l-4 [&_blockquote]:border-slate-300 [&_blockquote]:pl-3 [&_blockquote]:italic [&_blockquote]:my-2 [&_strong]:font-semibold">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {message.content || ''}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  )
}
