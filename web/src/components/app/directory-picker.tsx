'use client'

import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { ChevronRight, Folder, FolderPlus } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { api, ApiError, type DirectoryEntry, type DirectoryListing } from '@/lib/api'

export function DirectoryPicker({ value, onChange }: { value: string; onChange: (path: string) => void }) {
  const initialPath = useRef(value)
  const [browsePath, setBrowsePath] = useState(value)
  const [entries, setEntries] = useState<DirectoryEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [newFolderName, setNewFolderName] = useState('')
  const [creating, setCreating] = useState(false)
  const newFolderId = useId()

  const load = useCallback(async (path: string) => {
    setLoading(true)
    try {
      const listing = await api.get<DirectoryListing>(`/settings/directories?path=${encodeURIComponent(path)}`)
      setBrowsePath(listing.path)
      setEntries(listing.entries)
      setError(null)
    } catch (err) {
      setEntries([])
      setError(err instanceof ApiError ? err.message : 'Could not read folders')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load(initialPath.current)
  }, [load])

  async function createFolder() {
    const name = newFolderName.trim()
    if (!name) {
      toast.error('Enter a folder name')
      return
    }
    setCreating(true)
    try {
      await api.post<DirectoryEntry>('/settings/directories', { path: browsePath, name })
      setNewFolderName('')
      await load(browsePath)
      toast.success(`Folder "${name}" created`)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not create folder')
    } finally {
      setCreating(false)
    }
  }

  const segments = browsePath ? browsePath.split('/') : []

  return (
    <div className="space-y-3 rounded-md border p-3">
      <div className="flex flex-wrap items-center gap-1 text-sm">
        <button
          type="button"
          onClick={() => void load('')}
          className="rounded px-1.5 py-0.5 font-medium hover:bg-accent hover:text-accent-foreground"
        >
          Top folder
        </button>
        {segments.map((segment, index) => (
          <span key={segments.slice(0, index + 1).join('/')} className="flex items-center gap-1">
            <ChevronRight className="h-3 w-3 text-muted-foreground" />
            <button
              type="button"
              onClick={() => void load(segments.slice(0, index + 1).join('/'))}
              className="rounded px-1.5 py-0.5 font-medium hover:bg-accent hover:text-accent-foreground"
            >
              {segment}
            </button>
          </span>
        ))}
      </div>

      <div className="max-h-52 divide-y overflow-y-auto rounded-md border">
        {loading && <p className="px-3 py-2 text-sm text-muted-foreground">Loading…</p>}
        {!loading && error && (
          <div className="space-y-2 px-3 py-2">
            <p className="text-sm text-destructive">{error}</p>
            <Button type="button" variant="outline" size="sm" onClick={() => void load('')}>
              Go to top folder
            </Button>
          </div>
        )}
        {!loading && !error && entries.length === 0 && (
          <p className="px-3 py-2 text-sm text-muted-foreground">No folders here yet.</p>
        )}
        {!loading &&
          !error &&
          entries.map((entry) => (
            <button
              key={entry.path}
              type="button"
              onClick={() => void load(entry.path)}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent hover:text-accent-foreground"
            >
              <Folder className="h-4 w-4 text-muted-foreground" />
              {entry.name}
            </button>
          ))}
      </div>

      <div className="space-y-2">
        <Label htmlFor={newFolderId} className="text-xs text-muted-foreground">
          New folder here
        </Label>
        <div className="flex gap-2">
          <Input
            id={newFolderId}
            value={newFolderName}
            onChange={(e) => setNewFolderName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                void createFolder()
              }
            }}
            placeholder="e.g. 2026"
            disabled={Boolean(error)}
          />
          <Button type="button" variant="outline" onClick={() => void createFolder()} disabled={creating || Boolean(error)}>
            <FolderPlus className="mr-2 h-4 w-4" /> {creating ? 'Creating…' : 'Create'}
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="button"
          onClick={() => onChange(browsePath)}
          disabled={!browsePath || browsePath === value || Boolean(error)}
        >
          {browsePath && browsePath === value ? 'Selected' : 'Use this folder'}
        </Button>
        <p className="text-xs text-muted-foreground">
          {browsePath ? (
            <>
              Saving labels to <span className="font-medium text-foreground">{value}</span>
            </>
          ) : (
            'Open or create a folder — labels cannot be saved in the top folder itself.'
          )}
        </p>
      </div>
    </div>
  )
}
