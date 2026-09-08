'use client'

import { useId, useState } from 'react'
import { FileSpreadsheet } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { downloadUrl } from '@/lib/api'

export default function ReportsPage() {
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [status, setStatus] = useState('')

  const fromId = useId()
  const toId = useId()
  const statusId = useId()

  function download() {
    if (fromDate && toDate && fromDate > toDate) {
      toast.error('"From" date must be on or before the "To" date')
      return
    }
    const params = new URLSearchParams()
    if (fromDate) params.set('from_date', fromDate)
    if (toDate) params.set('to_date', toDate)
    if (status) params.set('status', status)
    const query = params.toString()
    window.location.href = downloadUrl(`/labels/report.xlsx${query ? `?${query}` : ''}`)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Reports</h1>
        <p className="text-sm text-muted-foreground">Download a label-wise report for any date range.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Label report</CardTitle>
          <CardDescription>
            One row per label with its status, tracking number, recipient, and cost fields. Leave the dates blank to
            include every label.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor={fromId}>From</Label>
              <Input id={fromId} type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor={toId}>To</Label>
              <Input id={toId} type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor={statusId}>Status</Label>
              <Select id={statusId} value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="">All statuses</option>
                <option value="created">Created</option>
                <option value="pending">Needs checking</option>
                <option value="failed">Failed</option>
                <option value="voided">Voided</option>
              </Select>
            </div>
          </div>

          <Button onClick={download}>
            <FileSpreadsheet className="mr-2 h-4 w-4" />
            Download report (.xlsx)
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
