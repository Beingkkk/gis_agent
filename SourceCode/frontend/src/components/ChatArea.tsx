import { useRef, useEffect } from 'react'
import type { ChatMessage as ChatMessageType } from '../types'
import ChatMessage from './ChatMessage'

interface ChatAreaProps {
  messages: ChatMessageType[]
  state: string
  isLoading: boolean
  onSelectTemplate: (templateId: string) => void
}

export default function ChatArea({
  messages,
  state,
  isLoading,
  onSelectTemplate,
}: ChatAreaProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const stateHint = {
    IDLE: '',
    INTENT_CONFIRM: '请点击上方候选模板确认意图',
    PARAM_COLLECT: '请在右栏填写参数',
    SCRIPT_PREVIEW: '请检查脚本预览，确认后执行',
    EXECUTING: '脚本执行中...',
    ERROR_RECOVERY: '执行出错，请查看诊断信息',
  }[state] || ''

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto p-4 space-y-1">
        {messages.length === 0 && (
          <div className="flex items-center justify-center h-full text-gray-400 text-sm">
            欢迎使用 GIS Agent，在下方输入需求或从左栏选择模板
          </div>
        )}
        {messages.map((msg, idx) => (
          <ChatMessage
            key={idx}
            message={msg}
            onSelectTemplate={onSelectTemplate}
          />
        ))}
        {isLoading && (
          <div className="flex justify-start mb-4">
            <div className="bg-white border border-gray-200 rounded-lg px-4 py-2.5">
              <div className="flex gap-1">
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:0.1s]" />
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:0.2s]" />
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {stateHint && (
        <div className="px-4 py-2 bg-primary-50 border-t border-primary-100">
          <p className="text-xs text-primary-700">{stateHint}</p>
        </div>
      )}
    </div>
  )
}
