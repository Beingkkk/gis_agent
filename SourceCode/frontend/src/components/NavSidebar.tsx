import { Link, useLocation } from 'react-router-dom'

interface NavItem {
  id: string
  label: string
  path: string
  icon: React.ReactNode
}

const navItems: NavItem[] = [
  {
    id: 'task',
    label: '模板库',
    path: '/',
    icon: (
      <svg fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
        <rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" />
        <rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" />
      </svg>
    ),
  },
  {
    id: 'pipeline',
    label: 'Pipeline',
    path: '/pipeline',
    icon: (
      <svg fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
        <path d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    ),
  },
  {
    id: 'generator',
    label: '模板生成器',
    path: '/generator',
    icon: (
      <svg fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
        <path d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
      </svg>
    ),
  },
]

export default function NavSidebar() {
  const location = useLocation()

  return (
    <nav className="w-14 flex-shrink-0 bg-white border-r border-slate-200 flex flex-col items-center py-4 z-20">
      {/* Logo */}
      <Link
        to="/"
        className="w-9 h-9 rounded-[10px] flex items-center justify-center mb-6 shadow-sm"
        style={{ background: 'linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%)' }}
        title="GIS Agent"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-[18px] h-[18px]">
          <path d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 7m0 13V7m0 0L9 7" />
        </svg>
      </Link>

      {/* Nav Items */}
      <div className="flex-1 flex flex-col gap-0.5 w-full">
        {navItems.map((item) => {
          const isActive = location.pathname === item.path
          return (
            <Link
              key={item.id}
              to={item.path}
              className={`relative w-full h-10 flex items-center justify-center transition-all duration-150 ${
                isActive
                  ? 'text-blue-600'
                  : 'text-slate-400 hover:text-slate-600 hover:bg-slate-50'
              }`}
              title={item.label}
            >
              {isActive && (
                <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 bg-blue-600 rounded-r-[3px]" />
              )}
              {item.icon}
            </Link>
          )
        })}
      </div>
    </nav>
  )
}
