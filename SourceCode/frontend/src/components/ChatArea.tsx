import { useRef, useEffect, useCallback } from 'react'
import { selectDirectory } from '../electron-api'
import type { ChatMessage as ChatMessageType } from '../types'
import ChatMessage from './ChatMessage'

interface ChatAreaProps {
  messages: ChatMessageType[]
  state: string
  isLoading: boolean
  workspace?: string | null
  onSelectTemplate: (templateId: string) => void
  onClearSession?: () => void
  onUpdateWorkspace?: (path: string) => void
}

function statusInfo(state: string): { text: string; sub: string; dotColor: string } {
  switch (state) {
    case 'IDLE':
      return { text: '探索中', sub: '', dotColor: 'bg-slate-300' }
    case 'INTENT_CONFIRM':
      return { text: '意图确认', sub: '请点击上方候选模板', dotColor: 'bg-amber-400' }
    case 'PARAM_COLLECT':
      return { text: '参数填写', sub: '请在右栏填写参数', dotColor: 'bg-blue-500' }
    case 'SCRIPT_PREVIEW':
      return { text: '脚本预览', sub: '请检查脚本预览，确认后执行', dotColor: 'bg-purple-500' }
    case 'EXECUTING':
      return { text: '执行中', sub: '脚本正在运行', dotColor: 'bg-emerald-500' }
    case 'ERROR_RECOVERY':
      return { text: '错误恢复', sub: '请查看诊断信息', dotColor: 'bg-red-500' }
    default:
      return { text: '就绪', sub: '', dotColor: 'bg-slate-300' }
  }
}

export default function ChatArea({
  messages,
  state,
  isLoading,
  workspace,
  onSelectTemplate,
  onClearSession,
  onUpdateWorkspace,
}: ChatAreaProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const { text, sub, dotColor } = statusInfo(state)
  const isActive = state === 'EXECUTING'

  const handleClear = useCallback(() => {
    if (window.confirm('确定要清空当前会话吗？')) {
      onClearSession?.()
    }
  }, [onClearSession])

  const handleBrowseClick = async () => {
    const path = await selectDirectory()
    if (path && path !== workspace) {
      onUpdateWorkspace?.(path)
    }
  }


  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Chat Header */}
      <div className="h-[52px] bg-white border-b border-slate-200 flex items-center justify-between px-5 flex-shrink-0">
        <div className="flex items-center gap-2">
          <div className={`w-[7px] h-[7px] rounded-full ${dotColor} ${isActive ? 'shadow-[0_0_0_3px_rgba(16,185,129,0.15)]' : ''} transition-all duration-300`} />
          <span className="text-[13px] font-medium text-slate-900">{text}</span>
          {sub && (
            <span className="text-xs text-slate-400 ml-1">{sub}</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* Workspace path — label + browse button */}
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1.5 text-xs">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-blue-400 flex-shrink-0">
                <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z" />
              </svg>
              <span className="font-mono text-slate-600 max-w-[200px] truncate" title={workspace || '未设置'}>
                {workspace || '未设置'}
              </span>
            </div>
            <button
              type="button"
              onClick={handleBrowseClick}
              className="h-7 px-2.5 rounded-md bg-white text-slate-500 text-[11px] hover:bg-blue-50 hover:text-blue-600 hover:border-blue-300 transition-colors border border-slate-200 font-medium"
            >
              浏览
            </button>
          </div>

          {onClearSession && (
            <button
              onClick={handleClear}
              className="w-[30px] h-[30px] rounded-[7px] flex items-center justify-center text-slate-400 hover:text-red-500 hover:bg-red-50 transition-all"
              title="清空会话"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-5 flex flex-col gap-4">
        {messages.length === 0 && (
          <div className="flex-1 flex items-center justify-center text-slate-400 text-sm">
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
          <div className="flex justify-start">
            <div className="flex gap-[3px] items-center">
              <span className="w-[5px] h-[5px] rounded-full bg-slate-400 animate-bounce" />
              <span className="w-[5px] h-[5px] rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '0.2s' }} />
              <span className="w-[5px] h-[5px] rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '0.4s' }} />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
