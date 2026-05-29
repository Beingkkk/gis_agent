import type { ChatMessage as ChatMessageType, CandidateTemplate } from '../types'

interface ChatMessageProps {
  message: ChatMessageType
  onSelectTemplate?: (templateId: string) => void
}

export default function ChatMessage({
  message,
  onSelectTemplate,
}: ChatMessageProps) {
  const isUser = message.role === 'user'

  if (message.type === 'cards' && message.meta?.candidates) {
    const candidates = message.meta.candidates as CandidateTemplate[]
    return (
      <div className="flex justify-start mb-4">
        <div className="max-w-[80%] space-y-2">
          <p className="text-sm text-gray-700">
            {message.content || '找到以下候选模板，请点击确认：'}
          </p>
          <div className="space-y-2">
            {candidates.map((t) => (
              <button
                key={t.id}
                onClick={() => onSelectTemplate?.(t.id)}
                className="w-full text-left rounded-lg border border-gray-200 bg-white p-3 hover:border-primary-500 hover:bg-primary-50 transition-colors"
              >
                <div className="text-sm font-medium text-gray-800">
                  {t.name}
                </div>
                <div className="text-xs text-gray-500 mt-0.5">
                  {t.description}
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    )
  }

  if (message.type === 'script') {
    return (
      <div className="flex justify-start mb-4">
        <div className="max-w-[90%] w-full">
          <pre className="bg-gray-800 text-gray-100 p-3 text-xs font-mono rounded-md overflow-x-auto whitespace-pre-wrap">
            {message.content}
          </pre>
        </div>
      </div>
    )
  }

  if (message.type === 'error') {
    return (
      <div className="flex justify-start mb-4">
        <div className="max-w-[80%] rounded-lg bg-red-50 border border-red-200 p-3">
          <p className="text-sm text-red-700">{message.content}</p>
        </div>
      </div>
    )
  }

  return (
    <div
      className={`flex mb-4 ${isUser ? 'justify-end' : 'justify-start'}`}
    >
      <div
        className={`max-w-[80%] rounded-lg px-4 py-2.5 ${
          isUser
            ? 'bg-primary-600 text-white'
            : 'bg-white border border-gray-200 text-gray-800'
        }`}
      >
        <p className="text-sm whitespace-pre-wrap">{message.content}</p>
      </div>
    </div>
  )
}
