'use client'

import { useEffect, useId, useState } from 'react'
import { toast } from 'sonner'

import { Field } from '@/components/app/field'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { api, ApiError, type SettingsOut } from '@/lib/api'

type FormState = Omit<SettingsOut, 'available_environments' | 'last_quota_available' | 'last_quota_checked_at'>

export default function SettingsPage() {
  const [form, setForm] = useState<FormState | null>(null)
  const [availableEnvironments, setAvailableEnvironments] = useState<string[]>([])
  const [saving, setSaving] = useState(false)

  const labelDirectoryId = useId()
  const defaultServiceCodeId = useId()
  const epgEnvironmentId = useId()

  useEffect(() => {
    api.get<SettingsOut>('/settings').then((data) => {
      const { available_environments, last_quota_available, last_quota_checked_at, ...rest } = data
      setForm(rest)
      setAvailableEnvironments(available_environments)
    })
  }, [])

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!form) return
    setSaving(true)
    try {
      const updated = await api.put<SettingsOut>('/settings', form)
      const { available_environments, last_quota_available, last_quota_checked_at, ...rest } = updated
      setForm(rest)
      setAvailableEnvironments(available_environments)
      toast.success('Settings saved')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  if (!form) return <p className="text-sm text-muted-foreground">Loading…</p>

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">Shipper address, label storage, and EPG environment.</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>From address</CardTitle>
            <CardDescription>Used on every label unless overridden at generation time.</CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Contact name" value={form.from_name} onChange={(v) => update('from_name', v)} />
            <Field label="Company" value={form.from_company} onChange={(v) => update('from_company', v)} required />
            <Field
              label="Address line 1"
              value={form.from_address1}
              onChange={(v) => update('from_address1', v)}
              required
              className="sm:col-span-2"
            />
            <Field
              label="Address line 2"
              value={form.from_address2 ?? ''}
              onChange={(v) => update('from_address2', v || null)}
              className="sm:col-span-2"
            />
            <Field label="City" value={form.from_city} onChange={(v) => update('from_city', v)} required />
            <Field label="State" value={form.from_state} onChange={(v) => update('from_state', v.toUpperCase())} required />
            <Field label="Postal code" value={form.from_postal_code} onChange={(v) => update('from_postal_code', v)} required />
            <Field label="Phone" value={form.from_phone ?? ''} onChange={(v) => update('from_phone', v || null)} />
            <Field label="Email" value={form.from_email ?? ''} onChange={(v) => update('from_email', v || null)} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Labels &amp; shipping</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor={labelDirectoryId}>Save directory</Label>
              <Input
                id={labelDirectoryId}
                value={form.label_directory}
                onChange={(e) => update('label_directory', e.target.value)}
                placeholder="labels"
              />
              <p className="text-xs text-muted-foreground">Relative to the storage volume, e.g. &quot;labels&quot;.</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor={defaultServiceCodeId}>Default service code</Label>
              <Select id={defaultServiceCodeId} value={form.default_service_code} onChange={(e) => update('default_service_code', e.target.value)}>
                <option value="EP03">EP03 — Domestic Priority Parcel</option>
                <option value="EP05">EP05 — Domestic eDGE</option>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor={epgEnvironmentId}>EPG environment</Label>
              <Select id={epgEnvironmentId} value={form.epg_environment} onChange={(e) => update('epg_environment', e.target.value)}>
                {availableEnvironments.map((env) => (
                  <option key={env} value={env}>
                    {env === 'sandbox' ? 'Sandbox' : 'Production'}
                  </option>
                ))}
              </Select>
              {availableEnvironments.length < 2 && (
                <p className="text-xs text-muted-foreground">
                  Only environments with a configured API key are selectable.
                </p>
              )}
            </div>
          </CardContent>
        </Card>

        <Button type="submit" disabled={saving}>
          {saving ? 'Saving…' : 'Save settings'}
        </Button>
      </form>
    </div>
  )
}
