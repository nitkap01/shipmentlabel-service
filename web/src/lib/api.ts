export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      ...(init?.body && !(init.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
  })

  if (!res.ok) {
    let message = `Request failed (${res.status})`
    try {
      const body = await res.json()
      message = body.detail || message
    } catch {
      // response had no JSON body
    }
    throw new ApiError(res.status, message)
  }

  if (res.status === 204) return undefined as T
  const contentType = res.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    return (await res.json()) as T
  }
  return undefined as T
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body !== undefined ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PUT', body: JSON.stringify(body) }),
  postForm: <T>(path: string, form: FormData) => request<T>(path, { method: 'POST', body: form }),
}

export function downloadUrl(path: string): string {
  return `/api${path}`
}

// --- Shared types (mirrors backend/app/schemas.py) ---

export interface LabelOut {
  id: number
  created_at: string
  status: 'pending' | 'created' | 'failed' | 'voided'
  source: 'single' | 'bulk'
  bulk_run_id: number | null
  service_code: string
  recipient_name: string
  recipient_company: string | null
  recipient_address1: string
  recipient_address2: string | null
  recipient_city: string
  recipient_state: string
  recipient_postal_code: string
  recipient_country: string
  recipient_phone: string | null
  recipient_email: string | null
  weight_value: string
  weight_unit: string
  weight_oz: string
  length_value: string | null
  width_value: string | null
  height_value: string | null
  dimension_unit: string | null
  declared_value: string
  currency_code: string
  reference1: string | null
  tracking_number: string | null
  unique_reference_id: string | null
  epg_error_code: string | null
  epg_error_message: string | null
  pdf_path: string | null
  voided_at: string | null
  void_error: string | null
  manifest_close_id: number | null
}

export interface LabelListResponse {
  items: LabelOut[]
  total: number
  page: number
  page_size: number
}

export interface LabelStats {
  total: number
  this_month: number
  voided: number
  needs_checking: number
}

export interface SettingsOut {
  from_name: string
  from_company: string
  from_address1: string
  from_address2: string | null
  from_city: string
  from_state: string
  from_postal_code: string
  from_country: string
  from_phone: string | null
  from_email: string | null
  label_directory: string
  default_service_code: string
  epg_environment: string
  available_environments: string[]
  last_quota_available: number | null
  last_quota_checked_at: string | null
}

export interface DirectoryEntry {
  name: string
  path: string
}

export interface DirectoryListing {
  path: string
  entries: DirectoryEntry[]
}

export interface BulkRunOut {
  id: number
  created_at: string
  started_at: string | null
  finished_at: string | null
  status: 'draft' | 'queued' | 'running' | 'completed' | 'completed_with_errors' | 'failed'
  source_filename: string
  total_rows: number
  valid_rows: number
  success_count: number
  failure_count: number
  error_message: string | null
}

export interface BulkUploadResponse {
  run: BulkRunOut
  row_errors: { row_number: number; error: string }[]
}

export interface ManifestCloseOut {
  id: number
  created_at: string
  finished_at: string | null
  status: 'pending' | 'completed' | 'failed'
  epg_environment: string
  account_number: string
  close_id: string | null
  close_reports: unknown
  candidate_label_ids: number[]
  error_message: string | null
  resolved_manually: boolean
  label_count: number
}

export interface ManifestOpenSummary {
  environment: string
  configured_account_number: string | null
  open_count: number
  epg_account_number: string | null
  epg_package_count: number | null
  epg_checked_at: string
  epg_error: string | null
  pending_close: ManifestCloseOut | null
}
