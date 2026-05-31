import { Link } from 'react-router-dom'
import type { SessionState } from '../types'

interface TopBarProps {
  state: SessionState
  workspace?: string
}

function stateLabel(state: SessionState): { text: string; color: string } {
  switch (state) {
    case 'IDLE':
      return { text: '就绪', color: 'bg-gray-100 text-gray-600' }
    case 'INTENT_CONFIRM':
      return { text: '意图确认', color: 'bg-yellow-100 text-yellow-700' }
    case 'PARAM_COLLECT':
      return { text: '参数填写', color: 'bg-blue-100 text-blue-700' }
    case 'SCRIPT_PREVIEW':
      return { text: '脚本预览', color: 'bg-purple-100 text-purple-700' }
    case 'EXECUTING':
      return { text: '执行中', color: 'bg-green-100 text-green-700' }
    case 'ERROR_RECOVERY':
      return { text: '错误恢复', color: 'bg-red-100 text-red-700' }
  }
}

export default function TopBar({ state, workspace }: TopBarProps) {
  const label = stateLabel(state)

  return (
    <header className="h-12 flex-shrink-0 border-b border-gray-200 bg-white px-4 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <span className="text-lg font-bold text-primary-700">GIS Agent</span>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${label.color}`}>
          {label.text}
        </span>
      </div>
      <div className="flex items-center gap-3">
        {workspace && (
          <div
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-blue-50 border border-blue-100"
            title={workspace}
          >
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="text-blue-500 flex-shrink-0"
            >
              <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z" />
            </svg>
            <span className="text-[11px] font-medium text-blue-700 max-w-[200px] truncate">
              {workspace}
            </span>
          </div>
        )}
        <Link
          to="/pipeline"
          className="text-xs text-primary-600 hover:text-primary-700"
        >
          Pipeline
        </Link>
        <Link
          to="/generator"
          className="text-xs text-primary-600 hover:text-primary-700"
        >
          模板生成器
        </Link>
      </div>
    </header>
  )
}
