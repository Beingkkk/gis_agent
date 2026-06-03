import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import type { SessionState } from '../types'

// Extend CSSProperties for Electron frameless window drag regions
declare module 'react' {
  interface CSSProperties {
    WebkitAppRegion?: 'drag' | 'no-drag'
  }
}
import {
  minimizeWindow,
  maximizeWindow,
  closeWindow,
  isWindowMaximized,
  onWindowStateChange,
} from '../electron-api'

interface TopBarProps {
  state?: SessionState
  title?: string
  backTo?: string
}

function stateLabel(state: SessionState): { text: string; color: string } {
  switch (state) {
    case 'IDLE':
      return { text: '就绪', color: 'bg-slate-100 text-slate-600' }
    case 'INTENT_CONFIRM':
      return { text: '意图确认', color: 'bg-amber-100 text-amber-700' }
    case 'PARAM_COLLECT':
      return { text: '参数填写', color: 'bg-blue-100 text-blue-700' }
    case 'SCRIPT_PREVIEW':
      return { text: '脚本预览', color: 'bg-violet-100 text-violet-700' }
    case 'EXECUTING':
      return { text: '执行中', color: 'bg-emerald-100 text-emerald-700' }
    case 'ERROR_RECOVERY':
      return { text: '错误恢复', color: 'bg-red-100 text-red-700' }
  }
}

/* ─── Window Control Buttons ───────────────────────────────── */

function WindowControls() {
  const [maximized, setMaximized] = useState(false)

  // Query initial state
  useEffect(() => {
    isWindowMaximized().then(setMaximized).catch(() => {})
  }, [])

  // Subscribe to real-time state changes from main process
  useEffect(() => {
    const unsubscribe = onWindowStateChange((st) => {
      setMaximized(st.isMaximized)
    })
    return unsubscribe
  }, [])

  const handleMaximize = useCallback(async () => {
    await maximizeWindow()
  }, [])

  return (
    <div className="flex items-center h-full" style={{ WebkitAppRegion: 'no-drag' }}>
      {/* Minimize */}
      <button
        onClick={() => minimizeWindow()}
        className="group relative h-full w-11 flex items-center justify-center text-gray-500 hover:bg-gray-100 active:bg-gray-200 transition-colors duration-150"
        title="最小化"
      >
        <svg
          width="12"
          height="12"
          viewBox="0 0 12 12"
          className="text-gray-500 group-hover:text-gray-700 transition-colors"
        >
          <rect x="1" y="5.5" width="10" height="1" rx="0.5" fill="currentColor" />
        </svg>
      </button>

      {/* Maximize / Restore */}
      <button
        onClick={handleMaximize}
        className="group relative h-full w-11 flex items-center justify-center text-gray-500 hover:bg-gray-100 active:bg-gray-200 transition-colors duration-150"
        title={maximized ? '还原' : '最大化'}
      >
        {maximized ? (
          <svg
            width="12"
            height="12"
            viewBox="0 0 12 12"
            className="text-gray-500 group-hover:text-gray-700 transition-colors"
          >
            <path
              d="M3 4.5V3a1 1 0 011-1h5a1 1 0 011 1v5a1 1 0 01-1 1H8"
              stroke="currentColor"
              strokeWidth="1"
              fill="none"
            />
            <rect
              x="1.5"
              y="4.5"
              width="6"
              height="6"
              rx="1"
              stroke="currentColor"
              strokeWidth="1"
              fill="none"
            />
          </svg>
        ) : (
          <svg
            width="12"
            height="12"
            viewBox="0 0 12 12"
            className="text-gray-500 group-hover:text-gray-700 transition-colors"
          >
            <rect
              x="1.5"
              y="1.5"
              width="9"
              height="9"
              rx="1"
              stroke="currentColor"
              strokeWidth="1"
              fill="none"
            />
          </svg>
        )}
      </button>

      {/* Close */}
      <button
        onClick={() => closeWindow()}
        className="group relative h-full w-11 flex items-center justify-center text-gray-500 hover:bg-red-500 hover:text-white active:bg-red-600 transition-colors duration-150"
        title="关闭"
      >
        <svg
          width="12"
          height="12"
          viewBox="0 0 12 12"
          className="text-gray-500 group-hover:text-white transition-colors"
        >
          <path
            d="M2 2l8 8M10 2L2 10"
            stroke="currentColor"
            strokeWidth="1.2"
            strokeLinecap="round"
          />
        </svg>
      </button>
    </div>
  )
}

/* ─── Main TopBar Component ────────────────────────────────── */

export default function TopBar({ state, title, backTo }: TopBarProps) {
  const label = state ? stateLabel(state) : null
  const isElectron = !!window.electron

  const handleDoubleClick = useCallback(() => {
    if (!isElectron) return
    maximizeWindow().catch(() => {})
  }, [isElectron])

  return (
    <header
      className="h-[38px] flex-shrink-0 border-b border-gray-200/80 bg-gradient-to-r from-white via-white to-slate-50/60 flex items-center select-none shadow-[0_1px_2px_rgba(0,0,0,0.02)]"
      style={{ WebkitAppRegion: 'drag' }}
    >
      {/* ── Left: Back button + App branding ── */}
      <div
        className="flex items-center gap-2.5 px-4 h-full flex-shrink-0"
        style={{ WebkitAppRegion: 'no-drag' }}
      >
        {backTo && (
          <Link
            to={backTo}
            className="flex items-center justify-center w-7 h-7 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-all duration-150"
            title="返回"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M19 12H5" />
              <path d="M12 19l-7-7 7-7" />
            </svg>
          </Link>
        )}
        <div className="w-[18px] h-[18px] rounded-[5px] flex items-center justify-center flex-shrink-0"
          style={{ background: 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)' }}
        >
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2L2 7l10 5 10-5-10-5z" />
            <path d="M2 17l10 5 10-5" />
            <path d="M2 12l10 5 10-5" />
          </svg>
        </div>
        <span className="text-[13px] font-bold text-slate-700 tracking-tight">GIS Agent</span>
      </div>

      {/* ── Center: Draggable region (state badge only) ── */}
      <div
        className="flex-1 flex items-center justify-center gap-2.5 h-full min-w-0 px-3"
        style={{ WebkitAppRegion: 'drag' }}
        onDoubleClick={handleDoubleClick}
      >
        {title ? (
          <span className="text-[13px] font-semibold text-slate-600 truncate">{title}</span>
        ) : (
          label && (
            <span
              className={`rounded-full px-2.5 py-[2px] text-[10px] font-semibold flex-shrink-0 ${label.color}`}
            >
              {label.text}
            </span>
          )
        )}
      </div>

      {/* ── Right: Nav links + Window controls ── */}
      <div
        className="flex items-center gap-0.5 h-full flex-shrink-0 pl-2"
        style={{ WebkitAppRegion: 'no-drag' }}
      >
        <div className="w-px h-4 bg-gray-200 mx-1.5" />

        {isElectron && <WindowControls />}
      </div>
    </header>
  )
}
