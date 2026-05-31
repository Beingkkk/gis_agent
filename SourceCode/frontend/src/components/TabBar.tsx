/**
 * TabBar: 三 TAB 切换栏（DC-UX-10）
 *
 * [🔍 模板识别] [💬 GIS 问答] [⚡ 脚本执行]
 *
 * Design: DC-UX-10, DC-UX-11, DC-UX-12, DC-UX-13
 */

import type { TabId } from '../types'

interface TabBarProps {
  activeTab: TabId
  qaMessageCount: number
  onTabChange: (tab: TabId) => void
}

const TABS: { id: TabId; label: string; icon: React.ReactNode }[] = [
  {
    id: 'discovery',
    label: '模板识别',
    icon: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="11" cy="11" r="8" />
        <line x1="21" y1="21" x2="16.65" y2="16.65" />
      </svg>
    ),
  },
  {
    id: 'qa',
    label: 'GIS 问答',
    icon: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
      </svg>
    ),
  },
  {
    id: 'exec',
    label: '脚本执行',
    icon: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
      </svg>
    ),
  },
]

export default function TabBar({ activeTab, qaMessageCount, onTabChange }: TabBarProps) {
  return (
    <div className="flex px-4 bg-white border-b border-slate-200 flex-shrink-0 gap-1">
      {TABS.map((tab) => {
        const isActive = activeTab === tab.id
        return (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={`relative px-4 py-2.5 text-[12.5px] font-semibold flex items-center gap-1.5 transition-colors cursor-pointer border-none bg-transparent
              ${isActive ? 'text-blue-700' : 'text-slate-400 hover:text-slate-600'}`}
          >
            {tab.icon}
            {tab.label}
            {tab.id === 'qa' && qaMessageCount > 0 && (
              <span
                className={`text-[9px] font-semibold px-[5px] py-[1px] rounded ${isActive ? 'bg-blue-100 text-blue-600' : 'bg-slate-100 text-slate-500'}`}
              >
                {qaMessageCount}
              </span>
            )}
            {/* Active underline */}
            {isActive && (
              <span className="absolute bottom-0 left-2 right-2 h-[2px] bg-blue-600 rounded-t-sm" />
            )}
          </button>
        )
      })}
    </div>
  )
}
