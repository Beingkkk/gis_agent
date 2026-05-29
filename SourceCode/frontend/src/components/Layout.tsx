import TopBar from './TopBar'
import type { SessionState } from '../types'

interface LayoutProps {
  state: SessionState
  children: React.ReactNode
  leftPanel: React.ReactNode
  rightPanel: React.ReactNode
}

export default function Layout({
  state,
  children,
  leftPanel,
  rightPanel,
}: LayoutProps) {
  return (
    <div className="h-full flex flex-col bg-gray-50">
      <TopBar state={state} />
      <div className="flex-1 flex overflow-hidden">
        {/* Left: Template cards */}
        <aside className="w-[280px] flex-shrink-0 border-r border-gray-200 bg-white overflow-y-auto">
          {leftPanel}
        </aside>

        {/* Center: Chat area */}
        <main className="flex-1 flex flex-col overflow-hidden">
          {children}
        </main>

        {/* Right: Detail panel */}
        <aside className="w-[360px] flex-shrink-0 border-l border-gray-200 bg-white overflow-y-auto">
          {rightPanel}
        </aside>
      </div>
    </div>
  )
}
