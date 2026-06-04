/**
 * QATab: GIS 问答 TAB（DC-UX-10）
 *
 * 职责：学习 GIS 概念、问参数含义、获取使用建议、错误诊断追问
 * 特点：累积多轮历史，有清空按钮；诊断前自动清空
 *
 * Design: DC-UX-10, DC-UX-12
 */

import { useState, useRef, useEffect } from 'react'
import ChatMessage from './ChatMessage'
import type { ChatMessage as ChatMessageType } from '../types'

interface QATabProps {
  messages: ChatMessageType[]
  isLoading: boolean
  isStreaming?: boolean
  lockedTemplateName?: string | null
  onSendMessage: (text: string) => void
  onClearMessages: () => void | Promise<void>
}

export default function QATab({
  messages,
  isLoading,
  isStreaming,
  lockedTemplateName,
  onSendMessage,
  onClearMessages,
}: QATabProps) {
  const [inputText, setInputText] = useState('')
  const [showClearConfirm, setShowClearConfirm] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Auto-scroll to bottom (skip when messages are cleared to avoid
  // smooth-scroll animation from a far scroll position blocking interaction)
  useEffect(() => {
    if (messages.length === 0) return
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current
    if (el) {
      el.style.height = 'auto'
      el.style.height = Math.min(el.scrollHeight, 120) + 'px'
    }
  }, [inputText])

  const handleSend = () => {
    const text = inputText.trim()
    if (!text) return
    setInputText('')
    onSendMessage(text)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleClearClick = () => {
    setShowClearConfirm(true)
  }

  const handleConfirmClear = async () => {
    setShowClearConfirm(false)
    await onClearMessages()
    textareaRef.current?.focus()
  }

  const handleCancelClear = () => {
    setShowClearConfirm(false)
    textareaRef.current?.focus()
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="h-[52px] bg-white border-b border-slate-200 flex items-center justify-between px-5 flex-shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-base font-medium text-slate-900">GIS 问答</span>
          {lockedTemplateName && (
            <span className="text-2xs px-2 py-[2px] rounded-md bg-blue-50 text-blue-600 border border-blue-100 font-medium truncate max-w-[180px]" title={`基于模板「${lockedTemplateName}」回答`}>
              📋 {lockedTemplateName}
            </span>
          )}
          {messages.length > 0 && (
            <span className="text-2xs px-1.5 py-[1px] rounded-full bg-slate-100 text-slate-400">
              {messages.length} 条
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* Clear button */}
          {messages.length > 0 && (
            <button
              onClick={handleClearClick}
              className="text-xs font-medium px-2.5 py-[5px] rounded-md border border-slate-200 text-slate-500 hover:text-red-600 hover:border-red-200 hover:bg-red-50 transition-all flex items-center gap-1"
              title="清空问答历史"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
              </svg>
              清空
            </button>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-5 flex flex-col gap-4">
        {messages.length === 0 && (
          <div className="flex-1 flex flex-col items-center justify-center text-slate-400">
            <div className="w-12 h-12 rounded-2xl bg-slate-100 flex items-center justify-center mb-3">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
              </svg>
            </div>
            <p className="text-sm">GIS 问答</p>
            <p className="text-xs text-slate-300 mt-1 text-center max-w-[280px]">
              询问 GIS 概念、工具用法、参数含义，或获取错误诊断帮助
            </p>
          </div>
        )}
        {messages.map((msg, idx) => (
          <ChatMessage
            key={idx}
            message={msg}
          />
        ))}
        {isLoading && !isStreaming && (
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

      {/* Input area */}
      <div className="border-t border-slate-200 bg-white px-5 py-3 flex-shrink-0">
        <div className="flex gap-2 items-end bg-white border border-slate-200 rounded-2xl px-3 py-1.5 shadow-sm focus-within:border-blue-500 focus-within:shadow-[0_0_0_3px_rgba(37,99,235,0.08),0_1px_3px_rgba(0,0,0,0.06)] transition-all">
          <textarea
            ref={textareaRef}
            rows={1}
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="提问 GIS 相关问题..."
            disabled={isLoading}
            className="flex-1 border-none outline-none resize-none text-sm leading-relaxed py-2 bg-transparent text-slate-900 min-h-[22px] max-h-[120px] disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={isLoading || !inputText.trim()}
            className="w-8 h-8 rounded-[10px] bg-blue-600 text-white flex items-center justify-center flex-shrink-0 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-[0_1px_4px_rgba(37,99,235,0.2)]"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        </div>
        <p className="text-xs text-slate-400 mt-2 text-center">
          按 Enter 发送，Shift + Enter 换行
        </p>
      </div>

      {/* Clear confirm dialog — replaces window.confirm() to avoid Electron focus bug */}
      {showClearConfirm && (
        <div
          className="absolute inset-0 bg-black/30 flex items-center justify-center z-50"
          onClick={handleCancelClear}
        >
          <div
            className="bg-white rounded-xl shadow-lg px-6 py-5 max-w-[320px] w-full mx-4"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-base font-semibold text-slate-900 mb-2">确认清空</h3>
            <p className="text-sm text-slate-500 leading-relaxed mb-5">
              确定要清空问答历史吗？清空后不可恢复。
            </p>
            <div className="flex gap-2 justify-end">
              <button
                onClick={handleCancelClear}
                className="text-sm px-3.5 py-1.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 transition-all"
              >
                取消
              </button>
              <button
                onClick={handleConfirmClear}
                className="text-sm px-3.5 py-1.5 rounded-lg bg-red-600 text-white hover:bg-red-700 transition-all"
              >
                确定清空
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
