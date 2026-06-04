/**
 * CmdEditor: 命令编辑器（DC-UX-11）
 *
 * Monaco 风格暗色编辑器，支持 bash 命令的直接编辑。
 * 提供行号显示、Tab 缩进、语法高亮（简单规则）、复制/刷新操作。
 *
 * Design: DC-UX-11（命令预览态）
 */

import { useState, useCallback, useRef } from 'react'

interface CmdEditorProps {
  /** 当前脚本内容 */
  script: string
  /** 脚本变更回调（启用编辑模式时提供） */
  onChange?: (script: string) => void
  /** 点击刷新按钮 */
  onRefresh?: () => void
  /** 是否只读（执行中/成功/失败态时只读） */
  readOnly?: boolean
  /** 未填完的必填参数列表（用于提示） */
  missingParams?: string[]
}


export default function CmdEditor({
  script,
  onChange,
  onRefresh,
  readOnly = false,
  missingParams,
}: CmdEditorProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [isHovered, setIsHovered] = useState(false)

  // 同步 textarea 滚动与行号滚动
  const handleScroll = useCallback(() => {
    const ta = textareaRef.current
    if (!ta) return
    const lineNumEl = ta.parentElement?.querySelector('.line-numbers') as HTMLElement
    if (lineNumEl) {
      lineNumEl.scrollTop = ta.scrollTop
    }
  }, [])

  // Tab 键插入空格而非切换焦点
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Tab') {
        e.preventDefault()
        const ta = e.currentTarget
        const start = ta.selectionStart
        const end = ta.selectionEnd
        const value = ta.value
        const newValue = value.substring(0, start) + '    ' + value.substring(end)
        ta.value = newValue
        ta.selectionStart = ta.selectionEnd = start + 4
        onChange?.(newValue)
      }
    },
    [onChange]
  )

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(script)
  }, [script])

  const lines = script.split('\n')
  const lineCount = lines.length

  return (
    <div
      className="rounded-xl overflow-hidden border border-slate-700/50 bg-[#0f172a] flex flex-col"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3.5 py-2 bg-[#1e293b] border-b border-white/[0.06]">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-slate-400 font-mono">
            bash
          </span>
          {missingParams && missingParams.length > 0 && (
            <span className="text-2xs px-2 py-[2px] rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
              还有 {missingParams.length} 个必填参数未填
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          {onRefresh && !readOnly && (
            <button
              onClick={onRefresh}
              className="text-xs font-medium text-slate-400 hover:text-blue-400 transition-colors flex items-center gap-1 px-2 py-1 rounded hover:bg-white/5"
              title="根据当前参数刷新命令"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="23 4 23 10 17 10" />
                <polyline points="1 20 1 14 7 14" />
                <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
              </svg>
              刷新
            </button>
          )}
          <button
            onClick={handleCopy}
            className="text-xs font-medium text-slate-400 hover:text-blue-400 transition-colors flex items-center gap-1 px-2 py-1 rounded hover:bg-white/5"
            title="复制命令"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
              <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
            </svg>
            复制
          </button>
        </div>
      </div>

      {/* Editor body */}
      <div className="relative flex flex-1 min-h-[120px] max-h-[400px]">
        {/* Line numbers */}
        <div className="line-numbers flex-shrink-0 w-[40px] bg-[#0f172a] border-r border-white/[0.04] overflow-hidden py-3 select-none">
          {Array.from({ length: lineCount }, (_, i) => (
            <div
              key={i}
              className="text-right pr-2 text-xs text-slate-600 font-mono leading-[22px]"
            >
              {i + 1}
            </div>
          ))}
        </div>

        {/* Textarea (editable layer) */}
        <textarea
          ref={textareaRef}
          value={script}
          onChange={(e) => onChange?.(e.target.value)}
          onKeyDown={handleKeyDown}
          onScroll={handleScroll}
          readOnly={readOnly}
          spellCheck={false}
          className={`flex-1 bg-transparent text-slate-200 p-3 text-sm font-mono leading-[22px] resize-none outline-none whitespace-pre
            ${readOnly ? 'cursor-default' : 'cursor-text'}
            ${isHovered && !readOnly ? 'bg-white/[0.01]' : ''}`}
          style={{ tabSize: 4 }}
        />
      </div>
    </div>
  )
}
