'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Search } from 'lucide-react'

import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { LabelStatusBadge } from '@/components/app/status-badge'
import { api, type LabelListResponse } from '@/lib/api'

const PAGE_SIZE = 25

export default function LabelsPage() {
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState<LabelListResponse | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    const params = new URLSearchParams()
    if (q) params.set('q', q)
    if (status) params.set('status', status)
    if (fromDate) params.set('from_date', fromDate)
    if (toDate) params.set('to_date', toDate)
    params.set('page', String(page))
    params.set('page_size', String(PAGE_SIZE))

    const timeout = setTimeout(() => {
      api
        .get<LabelListResponse>(`/labels?${params.toString()}`)
        .then(setData)
        .finally(() => setLoading(false))
    }, 250)
    return () => clearTimeout(timeout)
  }, [q, status, fromDate, toDate, page])

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Labels</h1>
        <p className="text-sm text-muted-foreground">Search by name, address, phone, or reference.</p>
      </div>

      <Card>
        <CardContent className="flex flex-col gap-3 pt-6 sm:flex-row sm:items-end">
          <div className="flex-1 space-y-2">
            <label className="text-xs font-medium text-muted-foreground">Search</label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                className="pl-9"
                placeholder="Name, address, phone, reference…"
                value={q}
                onChange={(e) => {
                  setPage(1)
                  setQ(e.target.value)
                }}
              />
            </div>
          </div>
          <div className="space-y-2">
            <label className="text-xs font-medium text-muted-foreground">Status</label>
            <Select
              value={status}
              onChange={(e) => {
                setPage(1)
                setStatus(e.target.value)
              }}
              className="w-40"
            >
              <option value="">All</option>
              <option value="created">Created</option>
              <option value="pending">Needs checking</option>
              <option value="failed">Failed</option>
              <option value="voided">Voided</option>
            </Select>
          </div>
          <div className="space-y-2">
            <label className="text-xs font-medium text-muted-foreground">From</label>
            <Input
              type="date"
              value={fromDate}
              onChange={(e) => {
                setPage(1)
                setFromDate(e.target.value)
              }}
            />
          </div>
          <div className="space-y-2">
            <label className="text-xs font-medium text-muted-foreground">To</label>
            <Input
              type="date"
              value={toDate}
              onChange={(e) => {
                setPage(1)
                setToDate(e.target.value)
              }}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Recipient</TableHead>
              <TableHead>Address</TableHead>
              <TableHead>Created</TableHead>
              <TableHead>Service</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Tracking</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!loading && data?.items.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground">
                  No labels found.
                </TableCell>
              </TableRow>
            )}
            {data?.items.map((label) => (
              <TableRow key={label.id}>
                <TableCell>
                  <Link href={`/labels/${label.id}`} className="font-medium text-primary hover:underline">
                    {label.recipient_name}
                  </Link>
                  {label.recipient_company && (
                    <div className="text-xs text-muted-foreground">{label.recipient_company}</div>
                  )}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {label.recipient_address1}, {label.recipient_city}, {label.recipient_state}{' '}
                  {label.recipient_postal_code}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {new Date(label.created_at).toLocaleString()}
                </TableCell>
                <TableCell>{label.service_code}</TableCell>
                <TableCell>
                  <LabelStatusBadge status={label.status} />
                </TableCell>
                <TableCell className="text-muted-foreground">{label.tracking_number ?? '—'}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>

      {data && data.total > PAGE_SIZE && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>
            Page {page} of {totalPages} — {data.total} labels
          </span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Previous
            </Button>
            <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
