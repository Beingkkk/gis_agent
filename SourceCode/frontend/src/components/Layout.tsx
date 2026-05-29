import NavSidebar from './NavSidebar'

interface LayoutProps {
  children: React.ReactNode
  leftPanel: React.ReactNode
  rightPanel: React.ReactNode
}

export default function Layout({
  children,
  leftPanel,
  rightPanel,
}: LayoutProps) {
  return (
    <div className="h-full flex bg-[#f8fafc]">
      {/* Left: Navigation */}
      <NavSidebar />

      {/* Main content area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: Template cards sidebar */}
        <aside className="w-[300px] flex-shrink-0 border-r border-slate-200 bg-white flex flex-col overflow-hidden">
          {leftPanel}
        </aside>

        {/* Center: Chat area */}
        <main className="flex-1 flex flex-col overflow-hidden min-w-[360px]">
          {children}
        </main>

        {/* Right: Detail panel */}
        <aside className="w-[360px] flex-shrink-0 border-l border-slate-200 bg-white flex flex-col overflow-hidden">
          {rightPanel}
        </aside>
      </div>
    </div>
  )
}
