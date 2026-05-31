/**
 * Layout: 两栏框架（DC-UX-13）
 *
 * 主交互区（flex-1）+ 参数/详情面板（580px）
 * 三 TAB 的切换由父组件（MainPage）控制
 *
 * Design: DC-UX-13
 */

interface LayoutProps {
  /** 主交互区内容（TabBar + 三 TAB 之一） */
  mainPanel: React.ReactNode
  /** 右侧面板（参数表单 / 模板详情） */
  rightPanel: React.ReactNode
}

export default function Layout({ mainPanel, rightPanel }: LayoutProps) {
  return (
    <div className="h-full flex bg-[#f8fafc]">
      {/* Main content area: 主交互区 + 右侧面板 */}
      <div className="flex-1 flex overflow-hidden">
        {/* 主交互区（TabBar + TAB 内容） */}
        <main className="flex-1 flex flex-col overflow-hidden min-w-[480px]">
          {mainPanel}
        </main>

        {/* Right: Detail panel (DC-UX-13: 580px) */}
        <aside className="w-[580px] flex-shrink-0 border-l border-slate-200 bg-white flex flex-col overflow-hidden">
          {rightPanel}
        </aside>
      </div>
    </div>
  )
}
