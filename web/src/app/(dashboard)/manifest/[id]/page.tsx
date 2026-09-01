'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { CloseStatusBadge } from '@/components/app/status-badge'
import { api, type LabelListResponse, type ManifestCloseOut } from '@/lib/api'

export default function ManifestCloseDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [close, setClose] = useState<ManifestCloseOut | null>(null)
  const [labels, setLabels] = useState<LabelListResponse | null>(null)

  function load() {
    api.get<ManifestCloseOut>(`/manifest/closes/${id}`).then(setClose)
    api.get<LabelListResponse>(`/labels?manifest_close_id=${id}&page_size=200`).then(setLabels)
  }

  useEffect(load, [id])

  if (!close) return <p className="text-sm text-muted-foreground">Loading…</p>

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Manifest close #{close.id}</h1>
        <CloseStatusBadge status={close.status} />
      </div>

      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Summary</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <Row label="Created" value={new Date(close.created_at).toLocaleString()} />
            <Row label="Finished" value={close.finished_at ? new Date(close.finished_at).toLocaleString() : '—'} />
            <Row label="Account number" value={close.account_number} />
            <Row label="Environment" value={close.epg_environment} />
            <Row label="Close ID" value={close.close_id ?? '—'} />
            <Row label="Items" value={String(close.label_count)} />
            <Row label="Resolved manually" value={close.resolved_manually ? 'Yes' : 'No'} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Close reports</CardTitle>
          </CardHeader>
          <CardContent>
            {close.error_message && <p className="mb-3 text-sm text-destructive">{close.error_message}</p>}
            <div className="overflow-x-auto rounded-md border bg-muted/30">
              <pre className="p-3 text-xs">{JSON.stringify(close.close_reports ?? null, null, 2)}</pre>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Attached labels</CardTitle>
        </CardHeader>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Recipient</TableHead>
              <TableHead>Address</TableHead>
              <TableHead>Created</TableHead>
              <TableHead>Service</TableHead>
              <TableHead>Tracking</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {labels?.items.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  No labels attached.
                </TableCell>
              </TableRow>
            )}
            {labels?.items.map((label) => (
              <TableRow key={label.id}>
                <TableCell>
                  <Link href={`/labels/${label.id}`} className="font-medium text-primary hover:underline">
                    {label.recipient_name}
                  </Link>
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {label.recipient_address1}, {label.recipient_city}, {label.recipient_state}{' '}
                  {label.recipient_postal_code}
                </TableCell>
                <TableCell className="text-muted-foreground">{new Date(label.created_at).toLocaleString()}</TableCell>
                <TableCell>{label.service_code}</TableCell>
                <TableCell className="text-muted-foreground">{label.tracking_number ?? '—'}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
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
