'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { LayoutDashboard, PackagePlus, FileSpreadsheet, Search, Settings, LogOut, Package } from 'lucide-react'

import { cn } from '@/lib/utils'
import { api } from '@/lib/api'

const links = [
  { href: '/', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/new', label: 'New Label', icon: PackagePlus },
  { href: '/bulk', label: 'Bulk Upload', icon: FileSpreadsheet },
  { href: '/labels', label: 'Labels', icon: Search },
  { href: '/settings', label: 'Settings', icon: Settings },
]

export function Nav() {
  const pathname = usePathname()
  const router = useRouter()

  async function handleLogout() {
    await api.post('/auth/logout')
    router.push('/login')
    router.refresh()
  }

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r bg-card">
      <div className="flex items-center gap-2 border-b px-5 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary/10 text-primary">
          <Package className="h-4 w-4" />
        </div>
        <div className="leading-tight">
          <p className="text-sm font-semibold">Shipment Labels</p>
          <p className="text-xs text-muted-foreground">Green Shadow Enterprises</p>
        </div>
      </div>
      <nav className="flex-1 space-y-1 p-3">
        {links.map(({ href, label, icon: Icon }) => {
          const active = href === '/' ? pathname === '/' : pathname.startsWith(href)
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                'flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                active ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          )
        })}
      </nav>
      <div className="border-t p-3">
        <button
          onClick={handleLogout}
          className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </button>
      </div>
    </aside>
  )
}
