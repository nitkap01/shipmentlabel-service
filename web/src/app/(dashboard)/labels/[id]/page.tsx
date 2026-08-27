'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { Download, Ban } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { LabelStatusBadge } from '@/components/app/status-badge'
import { api, ApiError, downloadUrl, type LabelOut } from '@/lib/api'

export default function LabelDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [label, setLabel] = useState<LabelOut | null>(null)
  const [voiding, setVoiding] = useState(false)

  function load() {
    api.get<LabelOut>(`/labels/${id}`).then(setLabel)
  }

  useEffect(load, [id])

  async function handleVoid() {
    if (!confirm('Void this label? This cannot be undone.')) return
    setVoiding(true)
    try {
      await api.post<LabelOut>(`/labels/${id}/void`)
      toast.success('Label voided')
      load()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Failed to void label')
    } finally {
      setVoiding(false)
    }
  }

  if (!label) return <p className="text-sm text-muted-foreground">Loading…</p>

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">Label #{label.id}</h1>
            <LabelStatusBadge status={label.status} />
          </div>
          <p className="text-sm text-muted-foreground">
            Created {new Date(label.created_at).toLocaleString()} · {label.source === 'bulk' ? 'Bulk upload' : 'Single label'}
          </p>
        </div>
        <div className="flex gap-2">
          {label.pdf_path && (
            <a href={downloadUrl(`/labels/${label.id}/pdf`)} target="_blank" rel="noreferrer">
              <Button variant="outline">
                <Download className="mr-2 h-4 w-4" /> Download PDF
              </Button>
            </a>
          )}
          {label.status !== 'voided' && label.unique_reference_id && (
            <Button variant="destructive" onClick={handleVoid} disabled={voiding}>
              <Ban className="mr-2 h-4 w-4" /> {voiding ? 'Voiding…' : 'Void label'}
            </Button>
          )}
        </div>
      </div>

      {label.epg_error_message && (
        <Card className="border-destructive/50 bg-destructive/5">
          <CardContent className="pt-6 text-sm text-destructive">{label.epg_error_message}</CardContent>
        </Card>
      )}
      {label.void_error && (
        <Card className="border-destructive/50 bg-destructive/5">
          <CardContent className="pt-6 text-sm text-destructive">Void failed: {label.void_error}</CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Recipient</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <p className="font-medium">{label.recipient_name}</p>
            {label.recipient_company && <p>{label.recipient_company}</p>}
            <p>{label.recipient_address1}</p>
            {label.recipient_address2 && <p>{label.recipient_address2}</p>}
            <p>
              {label.recipient_city}, {label.recipient_state} {label.recipient_postal_code}
            </p>
            {label.recipient_phone && <p className="text-muted-foreground">{label.recipient_phone}</p>}
            {label.recipient_email && <p className="text-muted-foreground">{label.recipient_email}</p>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Shipment</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <Row label="Service code" value={label.service_code} />
            <Row label="Weight" value={`${label.weight_value} ${label.weight_unit} (${label.weight_oz} oz)`} />
            {label.length_value && (
              <Row
                label="Dimensions"
                value={`${label.length_value} × ${label.width_value} × ${label.height_value} ${label.dimension_unit}`}
              />
            )}
            <Row label="Declared value" value={`${label.declared_value} ${label.currency_code}`} />
            {label.reference1 && <Row label="Reference" value={label.reference1} />}
            <Row label="Tracking number" value={label.tracking_number ?? '—'} />
            <Row label="EPG reference ID" value={label.unique_reference_id ?? '—'} />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  )
}
