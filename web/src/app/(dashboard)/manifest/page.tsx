'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { RefreshCw } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { CloseStatusBadge } from '@/components/app/status-badge'
import { api, ApiError, type LabelListResponse, type ManifestCloseOut, type ManifestOpenSummary } from '@/lib/api'

const PAGE_SIZE = 50

export default function ManifestPage() {
  const [summary, setSummary] = useState<ManifestOpenSummary | null>(null)
  const [openLabels, setOpenLabels] = useState<LabelListResponse | null>(null)
  const [history, setHistory] = useState<ManifestCloseOut[]>([])
  const [page, setPage] = useState(1)
  const [refreshing, setRefreshing] = useState(false)
  const [closing, setClosing] = useState(false)
  const [resolvingId, setResolvingId] = useState<number | null>(null)

  function loadSummary() {
    setRefreshing(true)
    api
      .get<ManifestOpenSummary>('/manifest/open')
      .then(setSummary)
      .finally(() => setRefreshing(false))
  }

  function loadOpenLabels() {
    const params = new URLSearchParams({
      open_only: 'true',
      page: String(page),
      page_size: String(PAGE_SIZE),
    })
    api.get<LabelListResponse>(`/labels?${params.toString()}`).then(setOpenLabels)
  }

  function loadHistory() {
    api.get<ManifestCloseOut[]>('/manifest/closes').then(setHistory)
  }

  useEffect(loadSummary, [])
  useEffect(loadOpenLabels, [page])
  useEffect(loadHistory, [])

  function handleRefresh() {
    loadSummary()
    loadOpenLabels()
  }

  async function handleClose() {
    if (!summary) return
    const confirmed = confirm(
      `Close the manifest for account ${summary.configured_account_number}? This finalizes ${summary.open_count} open package(s) at ePost Global and cannot be undone.`
    )
    if (!confirmed) return

    setClosing(true)
    try {
      await api.post<ManifestCloseOut>('/manifest/closes')
      toast.success('Manifest closed')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Failed to close manifest')
    } finally {
      setClosing(false)
      loadSummary()
      loadOpenLabels()
      loadHistory()
    }
  }

  async function handleResolve(closeId: number, outcome: 'completed' | 'failed') {
    setResolvingId(closeId)
    try {
      await api.post<ManifestCloseOut>(`/manifest/closes/${closeId}/resolve`, { outcome })
      toast.success(`Close #${closeId} marked ${outcome}`)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Failed to resolve close')
    } finally {
      setResolvingId(null)
      loadSummary()
      loadOpenLabels()
      loadHistory()
    }
  }

  if (!summary) return <p className="text-sm text-muted-foreground">Loading…</p>

  const noAccountNumber = !summary.configured_account_number
  const hasEpgCount = summary.epg_package_count !== null && summary.epg_package_count !== undefined
  const countMismatch = hasEpgCount && summary.epg_package_count !== summary.open_count
  const accountMismatch =
    !!summary.epg_account_number &&
    !!summary.configured_account_number &&
    summary.epg_account_number !== summary.configured_account_number
  const closeDisabled =
    closing ||
    noAccountNumber ||
    !!summary.pending_close ||
    (summary.open_count === 0 && (summary.epg_package_count ?? 0) === 0)
  const totalPages = openLabels ? Math.max(1, Math.ceil(openLabels.total / PAGE_SIZE)) : 1

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Opened Items</h1>
          <p className="text-sm text-muted-foreground">
            Labels not yet included in an EPG manifest close, for the {summary.environment} environment.
          </p>
        </div>
        <Button variant="outline" onClick={handleRefresh} disabled={refreshing}>
          <RefreshCw className="mr-2 h-4 w-4" /> {refreshing ? 'Refreshing…' : 'Refresh'}
        </Button>
      </div>

      <Card>
        <CardContent className="grid grid-cols-2 gap-4 pt-6 sm:grid-cols-4">
          <Stat label="Open in portal" value={String(summary.open_count)} />
          <Stat label="Open at EPG" value={summary.epg_error ? '—' : String(summary.epg_package_count ?? '—')} />
          <Stat label="Account number" value={summary.configured_account_number ?? 'Not captured yet'} />
          <Stat label="Last checked" value={new Date(summary.epg_checked_at).toLocaleString()} />
        </CardContent>
      </Card>

      {summary.epg_error && (
        <Card className="border-destructive/50 bg-destructive/5">
          <CardContent className="pt-6 text-sm text-destructive">
            Could not reach EPG to check the live open count: {summary.epg_error}
          </CardContent>
        </Card>
      )}

      {noAccountNumber && (
        <Card className="border-destructive/50 bg-destructive/5">
          <CardContent className="pt-6 text-sm text-destructive">
            No EPG account number captured yet for {summary.environment}. Ship or rate a label in this environment
            first — the account number is captured automatically from that response.
          </CardContent>
        </Card>
      )}

      {accountMismatch && (
        <Card className="border-destructive/50 bg-destructive/5">
          <CardContent className="pt-6 text-sm text-destructive">
            EPG reports account number {summary.epg_account_number}, but {summary.configured_account_number} is on
            file for {summary.environment}.
          </CardContent>
        </Card>
      )}

      {countMismatch && !noAccountNumber && (
        <Card className="border-destructive/50 bg-destructive/5">
          <CardContent className="pt-6 text-sm text-destructive">
            EPG reports {summary.epg_package_count} open package(s), but the portal lists {summary.open_count}.
          </CardContent>
        </Card>
      )}

      {summary.pending_close && (
        <Card className="border-destructive/50 bg-destructive/5">
          <CardContent className="space-y-3 pt-6 text-sm">
            <p className="text-destructive">
              Close #{summary.pending_close.id} did not get a clear answer from EPG and needs checking. EPG
              currently reports{' '}
              {summary.epg_error ? 'an unknown number of' : (summary.epg_package_count ?? 'an unknown number of')} open
              package(s) — use that to decide whether the close actually went through.
            </p>
            <div className="flex gap-2">
              <Button
                size="sm"
                onClick={() => handleResolve(summary.pending_close!.id, 'completed')}
                disabled={resolvingId === summary.pending_close.id}
              >
                Mark completed
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleResolve(summary.pending_close!.id, 'failed')}
                disabled={resolvingId === summary.pending_close.id}
              >
                Mark failed
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle>Open items</CardTitle>
          <Button onClick={handleClose} disabled={closeDisabled}>
            {closing ? 'Closing…' : `Close (${summary.open_count})`}
          </Button>
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
            {openLabels?.items.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  Nothing open right now.
                </TableCell>
              </TableRow>
            )}
            {openLabels?.items.map((label) => (
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

      {openLabels && openLabels.total > PAGE_SIZE && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>
            Page {page} of {totalPages} — {openLabels.total} open
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

      <Card>
        <CardHeader>
          <CardTitle>Close history</CardTitle>
        </CardHeader>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Closed at</TableHead>
              <TableHead>Account</TableHead>
              <TableHead>Environment</TableHead>
              <TableHead>Items</TableHead>
              <TableHead>Close ID</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {history.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground">
                  No closes yet.
                </TableCell>
              </TableRow>
            )}
            {history.map((close) => (
              <TableRow key={close.id}>
                <TableCell>
                  <Link href={`/manifest/${close.id}`} className="font-medium text-primary hover:underline">
                    {new Date(close.created_at).toLocaleString()}
                  </Link>
                </TableCell>
                <TableCell>{close.account_number}</TableCell>
                <TableCell className="text-muted-foreground">{close.epg_environment}</TableCell>
                <TableCell>{close.label_count}</TableCell>
                <TableCell className="text-muted-foreground">{close.close_id ?? '—'}</TableCell>
                <TableCell>
                  <CloseStatusBadge status={close.status} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-xl font-semibold">{value}</p>
    </div>
  )
}
