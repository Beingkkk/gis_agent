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
          <span className="text-xs text-gray-500">工作区: {workspace}</span>
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
