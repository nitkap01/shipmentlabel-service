'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Package, CalendarDays, Ban, AlertTriangle } from 'lucide-react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { api, type LabelStats, type SettingsOut } from '@/lib/api'

export default function DashboardPage() {
  const [stats, setStats] = useState<LabelStats | null>(null)
  const [settings, setSettings] = useState<SettingsOut | null>(null)

  useEffect(() => {
    api.get<LabelStats>('/labels/stats').then(setStats).catch(() => {})
    api.get<SettingsOut>('/settings').then(setSettings).catch(() => {})
  }, [])

  const tiles = [
    { label: 'Total labels', value: stats?.total, icon: Package },
    { label: 'This month', value: stats?.this_month, icon: CalendarDays },
    { label: 'Voided', value: stats?.voided, icon: Ban },
    { label: 'Needs checking', value: stats?.needs_checking, icon: AlertTriangle, warn: true },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="text-sm text-muted-foreground">Overview of shipment labels for Green Shadow Enterprises.</p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {tiles.map(({ label, value, icon: Icon, warn }) => (
          <Card key={label}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
              <Icon className={warn && value ? 'h-4 w-4 text-warning' : 'h-4 w-4 text-muted-foreground'} />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{value ?? '—'}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>EPG environment</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Active environment</span>
            <span className="font-medium capitalize">{settings?.epg_environment ?? '—'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Default service code</span>
            <span className="font-medium">{settings?.default_service_code ?? '—'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Last seen quota available</span>
            <span className="font-medium">{settings?.last_quota_available ?? '—'}</span>
          </div>
          <p className="pt-2 text-xs text-muted-foreground">
            Manage the shipper address, save directory, and environment in{' '}
            <Link href="/settings" className="text-primary underline underline-offset-2">
              Settings
            </Link>
            .
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
