import { ReactNode, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { UserButton } from '@clerk/clerk-react'
import {
  LayoutDashboard,
  Users,
  BarChart3,
  Target,
  MessageSquare,
  Upload,
  Settings,
  Menu,
  Calendar,
} from 'lucide-react'

interface NavItem {
  label: string
  href: string
  icon: React.ElementType
  phase: 1 | 2 | 3 | 4
  badge?: number
}

const NAV_ITEMS: NavItem[] = [
  { label: 'Home',     href: '/',        icon: LayoutDashboard, phase: 1 },
  { label: 'My Day',           href: '/my-day',           icon: Calendar, phase: 1 },
  { label: 'Commercial Queue', href: '/commercial-queue', icon: Target, phase: 1 },
  { label: 'Manager View',     href: '/manager',          icon: Users,  phase: 1 },
  { label: 'Users / Access',    href: '/users',            icon: Settings, phase: 1 },
  { label: 'Clients',  href: '/clients', icon: Users,           phase: 1 },
  { label: 'Sales',    href: '/sales',   icon: BarChart3,       phase: 2 },
  { label: 'Targets',  href: '/targets', icon: Target,          phase: 1 },
  { label: 'CRM',      href: '/crm',     icon: MessageSquare,   phase: 3 },
  { label: 'Import Queue', href: '/imports', icon: Upload,      phase: 1 },
]

interface AppLayoutProps {
  children: ReactNode
  importIssueCount?: number
}

export function AppLayout({ children, importIssueCount = 0 }: AppLayoutProps) {
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <div className="min-h-screen bg-gray-50 flex">
      {/* ── Sidebar ── */}
      <aside
        className={`
          fixed inset-y-0 left-0 z-50 w-56 bg-[#1F3864] text-white flex flex-col
          transform transition-transform duration-200
          ${mobileOpen ? 'translate-x-0' : '-translate-x-full'}
          md:relative md:translate-x-0
        `}
      >
        {/* Logo */}
        <div className="px-4 py-5 border-b border-[#2E5395]">
          <div className="text-sm font-semibold text-[#90CAF9] uppercase tracking-wider">
            Waterford Estate
          </div>
          <div className="text-xs text-[#5C8BC4] mt-0.5">Sales Intelligence</div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-2 py-4 space-y-0.5 overflow-y-auto">
          {NAV_ITEMS.map((item) => {
            const isActive = location.pathname === item.href ||
              (item.href !== '/' && location.pathname.startsWith(item.href))
            const isBuilt = item.phase === 1

            return (
              <Link
                key={item.href}
                to={isBuilt ? item.href : '#'}
                onClick={() => setMobileOpen(false)}
                className={`
                  flex items-center gap-3 px-3 py-2.5 rounded-md text-sm
                  transition-colors duration-100
                  ${isActive
                    ? 'bg-[#2E5395] text-white font-medium'
                    : isBuilt
                    ? 'text-[#90CAF9] hover:bg-[#2E5395] hover:text-white'
                    : 'text-[#4A6FA5] cursor-not-allowed opacity-60'
                  }
                `}
                title={!isBuilt ? `Available in Phase ${item.phase}` : undefined}
              >
                <item.icon size={16} className="flex-shrink-0" />
                <span>{item.label}</span>
                {item.label === 'Imports' && importIssueCount > 0 && (
                  <span className="ml-auto bg-[#E65100] text-white text-xs rounded-full px-1.5 py-0.5 min-w-[18px] text-center">
                    {importIssueCount}
                  </span>
                )}
                {!isBuilt && (
                  <span className="ml-auto text-[10px] text-[#4A6FA5]">P{item.phase}</span>
                )}
              </Link>
            )
          })}
        </nav>

        {/* User */}
        <div className="px-3 py-4 border-t border-[#2E5395] flex items-center gap-3">
          <UserButton afterSignOutUrl="/sign-in" />
          <div className="text-xs text-[#5C8BC4] truncate">
            FY2027 — Sep 2026
          </div>
        </div>
      </aside>

      {/* ── Mobile overlay ── */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 md:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* ── Main content ── */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Mobile header */}
        <header className="md:hidden bg-[#1F3864] text-white px-4 py-3 flex items-center justify-between">
          <button onClick={() => setMobileOpen(true)}>
            <Menu size={22} />
          </button>
          <span className="text-sm font-semibold">Waterford Estate</span>
          <UserButton afterSignOutUrl="/sign-in" />
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-auto p-4 md:p-6">
          {children}
        </main>
      </div>
    </div>
  )
}
