'use client'

// SHIP-8: file manager for the label PDFs (and bulk uploads) kept on the server, plus the S3 backup panel.

import { useCallback, useEffect, useId, useState } from 'react'
import Link from 'next/link'
import { ChevronRight, CloudUpload, Download, FileText, Folder, HardDriveDownload, RefreshCw, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { LabelStatusBadge } from '@/components/app/status-badge'
import { api, ApiError, downloadFile, downloadUrl } from '@/lib/api'

interface FolderEntry { name: string; path: string; file_count: number }
interface FileEntry {
  name: string
  path: string
  size: number
  modified: string
  label: { id: number; status: string; tracking_number: string | null; recipient_name: string } | null
}
interface Listing { path: string; folders: FolderEntry[]; files: FileEntry[] }
interface BackupStatus {
  last: {
    started_at: string; finished_at: string; ok: boolean; error: string | null; trigger: string; bucket: string
    db_copy_bytes: number; uploaded_files: number; total_files: number; total_bytes: number
  } | null
  queued: boolean
  db_copy_available: boolean
}

function size(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`
}

function when(iso: string) {
  return new Date(iso).toLocaleString()
}

export default function FilesPage() {
  const [path, setPath] = useState('')
  const [listing, setListing] = useState<Listing | null>(null)
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [confirmText, setConfirmText] = useState('')
  const [backup, setBackup] = useState<BackupStatus | null>(null)
  const confirmId = useId()

  const load = useCallback(() => {
    setLoading(true)
    api
      .get<Listing>(`/files?path=${encodeURIComponent(path)}`)
      .then((data) => {
        setListing(data)
        setSelected([])
        setConfirming(false)
      })
      .catch((err) => toast.error(err instanceof ApiError ? err.message : 'Could not open the folder'))
      .finally(() => setLoading(false))
  }, [path])

  const loadBackup = useCallback(() => api.get<BackupStatus>('/backup').then(setBackup).catch(() => {}), [])

  useEffect(load, [load])
  useEffect(() => {
    loadBackup()
  }, [loadBackup])
  useEffect(() => {
    if (!backup?.queued) return
    const t = setInterval(loadBackup, 4000) // a requested backup usually finishes in seconds
    return () => clearInterval(t)
  }, [backup?.queued, loadBackup])

  const crumbs = path ? path.split('/') : []
  const selectedFiles = selected.filter((p) => listing?.files.some((f) => f.path === p))
  const allPaths = [...(listing?.folders.map((f) => f.path) ?? []), ...(listing?.files.map((f) => f.path) ?? [])]
  const allSelected = allPaths.length > 0 && selected.length === allPaths.length

  function toggle(p: string) {
    setSelected((prev) => (prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]))
  }

  async function downloadSelected() {
    setBusy(true)
    try {
      await downloadFile('/files/zip', { paths: selected })
    } catch {
      toast.error('Could not download the selection')
    } finally {
      setBusy(false)
    }
  }

  async function deleteSelected() {
    setBusy(true)
    try {
      const res = await api.post<{ deleted: number; labels_updated: number }>('/files/delete', {
        paths: selectedFiles,
        confirm: confirmText,
      })
      toast.success(`Deleted ${res.deleted} file${res.deleted === 1 ? '' : 's'}` +
        (res.labels_updated ? ` (${res.labels_updated} label record${res.labels_updated === 1 ? '' : 's'} kept, marked "PDF removed")` : ''))
      setConfirmText('')
      load()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not delete')
    } finally {
      setBusy(false)
    }
  }

  async function backupNow() {
    try {
      await api.post('/backup/run')
      toast.success('Backup started - it uploads only new or changed files')
      loadBackup()
    } catch {
      toast.error('Could not start the backup')
    }
  }

  const last = backup?.last

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Files &amp; Backup</h1>
        <p className="text-sm text-muted-foreground">
          Label PDFs and uploads kept on the server. Select files or folders to download them; delete needs confirmation.
        </p>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle className="text-base">Backup to Amazon S3</CardTitle>
              <CardDescription>
                Every night and on request. Only new or changed files are uploaded; deleted files stay in the backup.
              </CardDescription>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" disabled={backup?.queued} onClick={backupNow}>
                <CloudUpload className="mr-2 h-4 w-4" />
                {backup?.queued ? 'Backing up…' : 'Back up now'}
              </Button>
              <a href={downloadUrl('/backup/download')}>
                <Button size="sm" variant="outline">
                  <HardDriveDownload className="mr-2 h-4 w-4" />
                  Download full backup
                </Button>
              </a>
            </div>
          </div>
        </CardHeader>
        <CardContent className="text-sm">
          {!last ? (
            <p className="text-muted-foreground">No backup has run yet.</p>
          ) : (
            <div className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-4">
              <div>
                <div className="text-xs text-muted-foreground">Last backup</div>
                <div className={last.ok ? '' : 'text-destructive'}>
                  {when(last.finished_at)} · {last.ok ? 'OK' : 'FAILED'}
                </div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Files backed up</div>
                <div>{last.total_files} ({size(last.total_bytes)})</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Uploaded that time</div>
                <div>{last.uploaded_files} new or changed</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Database copy</div>
                <div>{size(last.db_copy_bytes)}</div>
              </div>
              {last.error && <div className="col-span-full text-destructive">{last.error}</div>}
            </div>
          )}
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <nav aria-label="Folder" className="flex flex-wrap items-center gap-1 text-sm">
          <button className="font-medium hover:underline" onClick={() => setPath('')}>Storage</button>
          {crumbs.map((part, i) => (
            <span key={i} className="flex items-center gap-1">
              <ChevronRight className="h-4 w-4 text-muted-foreground" />
              <button className="hover:underline" onClick={() => setPath(crumbs.slice(0, i + 1).join('/'))}>{part}</button>
            </span>
          ))}
          <Button size="icon" variant="ghost" aria-label="Refresh" onClick={load} className="h-8 w-8">
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </nav>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-muted-foreground">{selected.length > 0 ? `${selected.length} selected` : ''}</span>
          <Button size="sm" disabled={selected.length === 0 || busy} onClick={downloadSelected}>
            <Download className="mr-2 h-4 w-4" />
            Download selected
          </Button>
          <Button size="sm" variant="destructive" disabled={selectedFiles.length === 0 || busy}
                  onClick={() => { setConfirming(true); setConfirmText('') }}>
            <Trash2 className="mr-2 h-4 w-4" />
            Delete
          </Button>
        </div>
      </div>

      {confirming && (
        <Card className="border-destructive">
          <CardContent className="space-y-3 pt-6 text-sm">
            <p>
              Delete <strong>{selectedFiles.length}</strong> file{selectedFiles.length === 1 ? '' : 's'} from the server?
              Label records stay (marked &ldquo;PDF removed&rdquo;) and copies already backed up stay in S3. Folders are not deleted.
            </p>
            <div className="flex flex-wrap items-end gap-2">
              <div className="space-y-1">
                <label htmlFor={confirmId} className="text-xs text-muted-foreground">Type DELETE to confirm</label>
                <Input id={confirmId} value={confirmText} onChange={(e) => setConfirmText(e.target.value)} className="w-40" />
              </div>
              <Button variant="destructive" disabled={confirmText !== 'DELETE' || busy} onClick={deleteSelected}>
                Delete files
              </Button>
              <Button variant="outline" onClick={() => setConfirming(false)}>Cancel</Button>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10">
                <input type="checkbox" aria-label="Select everything in this folder" checked={allSelected}
                       disabled={allPaths.length === 0} onChange={(e) => setSelected(e.target.checked ? allPaths : [])} />
              </TableHead>
              <TableHead>Name</TableHead>
              <TableHead>Label</TableHead>
              <TableHead className="text-right">Size</TableHead>
              <TableHead>Modified</TableHead>
              <TableHead className="w-12" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {listing && listing.folders.length === 0 && listing.files.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">This folder is empty.</TableCell>
              </TableRow>
            )}
            {listing?.folders.map((f) => (
              <TableRow key={f.path}>
                <TableCell>
                  <input type="checkbox" aria-label={`Select folder ${f.name}`} checked={selected.includes(f.path)}
                         onChange={() => toggle(f.path)} />
                </TableCell>
                <TableCell>
                  <button className="flex items-center gap-2 font-medium hover:underline" onClick={() => setPath(f.path)}>
                    <Folder className="h-4 w-4 text-muted-foreground" />
                    {f.name}
                  </button>
                </TableCell>
                <TableCell className="text-muted-foreground">{f.file_count} file{f.file_count === 1 ? '' : 's'}</TableCell>
                <TableCell />
                <TableCell />
                <TableCell />
              </TableRow>
            ))}
            {listing?.files.map((f) => (
              <TableRow key={f.path}>
                <TableCell>
                  <input type="checkbox" aria-label={`Select ${f.name}`} checked={selected.includes(f.path)}
                         onChange={() => toggle(f.path)} />
                </TableCell>
                <TableCell>
                  <span className="flex items-center gap-2">
                    <FileText className="h-4 w-4 text-muted-foreground" />
                    {f.name}
                  </span>
                </TableCell>
                <TableCell>
                  {f.label ? (
                    <span className="flex flex-wrap items-center gap-2">
                      <Link href={`/labels/${f.label.id}`} className="hover:underline">#{f.label.id}</Link>
                      <span className="text-muted-foreground">{f.label.recipient_name}</span>
                      <LabelStatusBadge status={f.label.status} />
                    </span>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell className="text-right tabular-nums">{size(f.size)}</TableCell>
                <TableCell className="text-muted-foreground">{when(f.modified)}</TableCell>
                <TableCell>
                  <a href={downloadUrl(`/files/file?path=${encodeURIComponent(f.path)}`)} aria-label={`Download ${f.name}`}>
                    <Download className="h-4 w-4" />
                  </a>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  )
}
