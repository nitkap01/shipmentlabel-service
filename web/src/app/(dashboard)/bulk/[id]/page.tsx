'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { Download, PackageCheck } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { RunStatusBadge } from '@/components/app/status-badge'
import { api, ApiError, downloadUrl, type BulkRunOut } from '@/lib/api'

const POLL_INTERVAL_MS = 2000
const ACTIVE_STATUSES = new Set(['queued', 'running'])

export default function BulkRunDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [run, setRun] = useState<BulkRunOut | null>(null)
  const [starting, setStarting] = useState(false)

  function load() {
    api.get<BulkRunOut>(`/bulk/runs/${id}`).then(setRun)
  }

  useEffect(load, [id])

  useEffect(() => {
    if (!run || !ACTIVE_STATUSES.has(run.status)) return
    const interval = setInterval(load, POLL_INTERVAL_MS)
    return () => clearInterval(interval)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run?.status])

  async function handleStart() {
    if (!run) return
    if (!confirm(`Generate ${run.valid_rows} label(s)? This will spend EPG quota and cannot be undone.`)) return
    setStarting(true)
    try {
      await api.post<BulkRunOut>(`/bulk/runs/${id}/start`)
      toast.success('Run started')
      load()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Failed to start run')
    } finally {
      setStarting(false)
    }
  }

  if (!run) return <p className="text-sm text-muted-foreground">Loading…</p>

  const isDraft = run.status === 'draft'
  const isActive = ACTIVE_STATUSES.has(run.status)
  const isDone = !isDraft && !isActive
  const processed = run.success_count + run.failure_count

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">{run.source_filename}</h1>
        <RunStatusBadge status={run.status} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{isDraft ? 'Preview' : isActive ? 'Progress' : 'Result'}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Stat label="Total rows" value={run.total_rows} />
            <Stat label="Valid rows" value={run.valid_rows} />
            <Stat label="Succeeded" value={run.success_count} />
            <Stat label="Failed / invalid" value={run.failure_count} />
          </div>

          {isActive && (
            <p className="text-sm text-muted-foreground">
              Processing… {processed} of {run.valid_rows} rows handled so far.
            </p>
          )}

          {run.error_message && <p className="text-sm text-destructive">{run.error_message}</p>}

          {isDraft && (
            <Button onClick={handleStart} disabled={starting || run.valid_rows === 0}>
              <PackageCheck className="mr-2 h-4 w-4" />
              {starting ? 'Starting…' : `Generate ${run.valid_rows} label(s)`}
            </Button>
          )}

          {isDone && (
            <div className="flex flex-wrap gap-2">
              <a href={downloadUrl(`/bulk/runs/${id}/report.xlsx`)}>
                <Button variant="outline">
                  <Download className="mr-2 h-4 w-4" /> Download report
                </Button>
              </a>
              {run.success_count > 0 && (
                <a href={downloadUrl(`/bulk/runs/${id}/labels.zip`)}>
                  <Button variant="outline">
                    <Download className="mr-2 h-4 w-4" /> Download labels (.zip)
                  </Button>
                </a>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-xl font-semibold">{value}</p>
    </div>
  )
}
