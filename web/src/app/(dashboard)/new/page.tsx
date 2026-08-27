'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { api, ApiError, type LabelOut } from '@/lib/api'
import { US_STATE_CODES } from '@/lib/us-states'

const emptyForm = {
  recipient_name: '',
  recipient_company: '',
  recipient_address1: '',
  recipient_address2: '',
  recipient_city: '',
  recipient_state: '',
  recipient_postal_code: '',
  recipient_phone: '',
  recipient_email: '',
  weight_value: '',
  weight_unit: 'oz',
  length_value: '',
  width_value: '',
  height_value: '',
  dimension_unit: 'inch',
  declared_value: '',
  reference1: '',
  service_code: '',
}

export default function NewLabelPage() {
  const router = useRouter()
  const [form, setForm] = useState(emptyForm)
  const [useDimensions, setUseDimensions] = useState(false)
  const [overrideFrom, setOverrideFrom] = useState(false)
  const [fromOverride, setFromOverride] = useState({
    name: '',
    company: '',
    address1: '',
    address2: '',
    city: '',
    state: '',
    postal_code: '',
    phone: '',
    email: '',
  })
  const [submitting, setSubmitting] = useState(false)

  function set<K extends keyof typeof form>(key: K, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    try {
      const payload: Record<string, unknown> = {
        recipient_name: form.recipient_name,
        recipient_company: form.recipient_company || null,
        recipient_address1: form.recipient_address1,
        recipient_address2: form.recipient_address2 || null,
        recipient_city: form.recipient_city,
        recipient_state: form.recipient_state,
        recipient_postal_code: form.recipient_postal_code,
        recipient_phone: form.recipient_phone || null,
        recipient_email: form.recipient_email || null,
        weight_value: Number(form.weight_value),
        weight_unit: form.weight_unit,
        declared_value: Number(form.declared_value),
        reference1: form.reference1 || null,
        service_code: form.service_code || null,
      }
      if (useDimensions) {
        payload.length_value = Number(form.length_value)
        payload.width_value = Number(form.width_value)
        payload.height_value = Number(form.height_value)
        payload.dimension_unit = form.dimension_unit
      }
      if (overrideFrom) {
        payload.from_override = {
          name: fromOverride.name || null,
          company: fromOverride.company,
          address1: fromOverride.address1,
          address2: fromOverride.address2 || null,
          city: fromOverride.city,
          state: fromOverride.state,
          postal_code: fromOverride.postal_code,
          phone: fromOverride.phone || null,
          email: fromOverride.email || null,
        }
      }

      const label = await api.post<LabelOut>('/labels', payload)
      if (label.status === 'created') {
        toast.success(`Label #${label.id} created — tracking ${label.tracking_number}`)
      } else {
        toast.warning(`Label #${label.id} saved with status "${label.status}" — check details`)
      }
      router.push(`/labels/${label.id}`)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Failed to create label')
      setSubmitting(false)
    }
  }

  const referenceLength = form.reference1.length
  const referenceHint =
    referenceLength === 0
      ? null
      : referenceLength <= 22
        ? 'Renders as a scannable barcode on the label.'
        : '23+ characters renders as plain text, not a barcode.'

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">New label</h1>
        <p className="text-sm text-muted-foreground">Create a single domestic shipment label.</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Recipient</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Name" value={form.recipient_name} onChange={(v) => set('recipient_name', v)} required />
            <Field label="Company" value={form.recipient_company} onChange={(v) => set('recipient_company', v)} />
            <Field
              label="Address line 1"
              value={form.recipient_address1}
              onChange={(v) => set('recipient_address1', v)}
              required
              className="sm:col-span-2"
            />
            <Field
              label="Address line 2"
              value={form.recipient_address2}
              onChange={(v) => set('recipient_address2', v)}
              className="sm:col-span-2"
            />
            <Field label="City" value={form.recipient_city} onChange={(v) => set('recipient_city', v)} required />
            <div className="space-y-2">
              <Label>State</Label>
              <Select value={form.recipient_state} onChange={(e) => set('recipient_state', e.target.value)} required>
                <option value="">Select…</option>
                {US_STATE_CODES.map((code) => (
                  <option key={code} value={code}>
                    {code}
                  </option>
                ))}
              </Select>
            </div>
            <Field
              label="Postal code"
              value={form.recipient_postal_code}
              onChange={(v) => set('recipient_postal_code', v)}
              required
            />
            <Field label="Phone" value={form.recipient_phone} onChange={(v) => set('recipient_phone', v)} />
            <Field label="Email" value={form.recipient_email} onChange={(v) => set('recipient_email', v)} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Package</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>Weight</Label>
                <div className="flex gap-2">
                  <Input
                    type="number"
                    step="0.01"
                    min="0"
                    value={form.weight_value}
                    onChange={(e) => set('weight_value', e.target.value)}
                    required
                  />
                  <Select value={form.weight_unit} onChange={(e) => set('weight_unit', e.target.value)} className="w-28">
                    <option value="oz">oz</option>
                    <option value="lb">lb</option>
                    <option value="kg">kg</option>
                  </Select>
                </div>
              </div>
              <Field
                label="Declared value (USD)"
                type="number"
                value={form.declared_value}
                onChange={(v) => set('declared_value', v)}
                required
              />
            </div>

            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={useDimensions} onChange={(e) => setUseDimensions(e.target.checked)} />
              Add dimensions
            </label>

            {useDimensions && (
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <Field label="Length" type="number" value={form.length_value} onChange={(v) => set('length_value', v)} />
                <Field label="Width" type="number" value={form.width_value} onChange={(v) => set('width_value', v)} />
                <Field label="Height" type="number" value={form.height_value} onChange={(v) => set('height_value', v)} />
                <div className="space-y-2">
                  <Label>Unit</Label>
                  <Select value={form.dimension_unit} onChange={(e) => set('dimension_unit', e.target.value)}>
                    <option value="inch">inch</option>
                    <option value="cm">cm</option>
                  </Select>
                </div>
              </div>
            )}

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>Reference / order #</Label>
                <Input value={form.reference1} onChange={(e) => set('reference1', e.target.value)} maxLength={50} />
                {referenceHint && <p className="text-xs text-muted-foreground">{referenceHint}</p>}
              </div>
              <div className="space-y-2">
                <Label>Service code</Label>
                <Select value={form.service_code} onChange={(e) => set('service_code', e.target.value)}>
                  <option value="">Use account default</option>
                  <option value="EP03">EP03 — Domestic Priority Parcel</option>
                  <option value="EP05">EP05 — Domestic eDGE</option>
                </Select>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>From address</CardTitle>
            <CardDescription>Uses the address in Settings unless overridden here.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={overrideFrom} onChange={(e) => setOverrideFrom(e.target.checked)} />
              Override for this label
            </label>
            {overrideFrom && (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field label="Contact name" value={fromOverride.name} onChange={(v) => setFromOverride((p) => ({ ...p, name: v }))} />
                <Field
                  label="Company"
                  value={fromOverride.company}
                  onChange={(v) => setFromOverride((p) => ({ ...p, company: v }))}
                  required
                />
                <Field
                  label="Address line 1"
                  value={fromOverride.address1}
                  onChange={(v) => setFromOverride((p) => ({ ...p, address1: v }))}
                  required
                  className="sm:col-span-2"
                />
                <Field
                  label="Address line 2"
                  value={fromOverride.address2}
                  onChange={(v) => setFromOverride((p) => ({ ...p, address2: v }))}
                  className="sm:col-span-2"
                />
                <Field label="City" value={fromOverride.city} onChange={(v) => setFromOverride((p) => ({ ...p, city: v }))} required />
                <Field
                  label="State"
                  value={fromOverride.state}
                  onChange={(v) => setFromOverride((p) => ({ ...p, state: v.toUpperCase() }))}
                  required
                />
                <Field
                  label="Postal code"
                  value={fromOverride.postal_code}
                  onChange={(v) => setFromOverride((p) => ({ ...p, postal_code: v }))}
                  required
                />
                <Field label="Phone" value={fromOverride.phone} onChange={(v) => setFromOverride((p) => ({ ...p, phone: v }))} />
              </div>
            )}
          </CardContent>
        </Card>

        <Button type="submit" size="lg" disabled={submitting}>
          {submitting ? 'Generating…' : 'Generate label'}
        </Button>
      </form>
    </div>
  )
}

function Field({
  label,
  value,
  onChange,
  required,
  className,
  type = 'text',
}: {
  label: string
  value: string
  onChange: (value: string) => void
  required?: boolean
  className?: string
  type?: string
}) {
  return (
    <div className={`space-y-2 ${className ?? ''}`}>
      <Label>{label}</Label>
      <Input type={type} value={value} onChange={(e) => onChange(e.target.value)} required={required} />
    </div>
  )
}
