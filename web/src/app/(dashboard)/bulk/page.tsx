'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Download, Upload } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { RunStatusBadge } from '@/components/app/status-badge'
import { api, ApiError, downloadUrl, type BulkRunOut, type BulkUploadResponse } from '@/lib/api'

export default function BulkUploadPage() {
  const router = useRouter()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [weightOverride, setWeightOverride] = useState('')
  const [dimensionOverride, setDimensionOverride] = useState('')
  const [uploading, setUploading] = useState(false)
  const [runs, setRuns] = useState<BulkRunOut[]>([])

  function loadRuns() {
    api.get<BulkRunOut[]>('/bulk/runs').then(setRuns)
  }

  useEffect(loadRuns, [])

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault()
    const file = fileInputRef.current?.files?.[0]
    if (!file) {
      toast.error('Choose a file first')
      return
    }
    setUploading(true)
    try {
      const form = new FormData()
      form.append('file', file)
      if (weightOverride) form.append('weight_unit_override', weightOverride)
      if (dimensionOverride) form.append('dimension_unit_override', dimensionOverride)

      const result = await api.postForm<BulkUploadResponse>('/bulk/uploads', form)
      toast.success(`${result.run.valid_rows} of ${result.run.total_rows} rows valid`)
      router.push(`/bulk/${result.run.id}`)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Bulk upload</h1>
        <p className="text-sm text-muted-foreground">Generate many labels at once from an Excel file.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Upload a file</CardTitle>
          <CardDescription>
            Use the exact template —{' '}
            <a href={downloadUrl('/bulk/template')} className="text-primary underline underline-offset-2">
              download it here
            </a>
            .
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleUpload} className="space-y-4">
            <div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx,.xls"
                className="block w-full text-sm file:mr-4 file:rounded-md file:border-0 file:bg-primary file:px-4 file:py-2 file:text-sm file:font-medium file:text-primary-foreground hover:file:bg-primary/90"
              />
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <label className="text-xs font-medium text-muted-foreground">
                  Weight unit override (optional — overrides every row&apos;s unit column)
                </label>
                <Select value={weightOverride} onChange={(e) => setWeightOverride(e.target.value)}>
                  <option value="">Use each row&apos;s own unit</option>
                  <option value="oz">oz</option>
                  <option value="lb">lb</option>
                  <option value="kg">kg</option>
                </Select>
              </div>
              <div className="space-y-2">
                <label className="text-xs font-medium text-muted-foreground">
                  Dimension unit override (optional)
                </label>
                <Select value={dimensionOverride} onChange={(e) => setDimensionOverride(e.target.value)}>
                  <option value="">Use each row&apos;s own unit</option>
                  <option value="inch">inch</option>
                  <option value="cm">cm</option>
                </Select>
              </div>
            </div>
            <Button type="submit" disabled={uploading}>
              <Upload className="mr-2 h-4 w-4" /> {uploading ? 'Uploading…' : 'Upload & preview'}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Run history</CardTitle>
        </CardHeader>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>File</TableHead>
              <TableHead>Created</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Rows</TableHead>
              <TableHead>Success</TableHead>
              <TableHead>Failed</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {runs.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground">
                  No bulk runs yet.
                </TableCell>
              </TableRow>
            )}
            {runs.map((run) => (
              <TableRow key={run.id}>
                <TableCell>
                  <Link href={`/bulk/${run.id}`} className="font-medium text-primary hover:underline">
                    {run.source_filename}
                  </Link>
                </TableCell>
                <TableCell className="text-muted-foreground">{new Date(run.created_at).toLocaleString()}</TableCell>
                <TableCell>
                  <RunStatusBadge status={run.status} />
                </TableCell>
                <TableCell>{run.total_rows}</TableCell>
                <TableCell>{run.success_count}</TableCell>
                <TableCell>{run.failure_count}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  )
}
