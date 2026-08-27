import { Badge } from '@/components/ui/badge'

const LABEL_STATUS_VARIANTS: Record<string, 'success' | 'destructive' | 'warning' | 'secondary'> = {
  created: 'success',
  failed: 'destructive',
  pending: 'warning',
  voided: 'secondary',
}

const RUN_STATUS_VARIANTS: Record<string, 'success' | 'destructive' | 'warning' | 'secondary'> = {
  completed: 'success',
  completed_with_errors: 'warning',
  failed: 'destructive',
  running: 'warning',
  queued: 'secondary',
  draft: 'secondary',
}

const LABEL_STATUS_TEXT: Record<string, string> = {
  created: 'Created',
  failed: 'Failed',
  pending: 'Needs checking',
  voided: 'Voided',
}

const RUN_STATUS_TEXT: Record<string, string> = {
  completed: 'Completed',
  completed_with_errors: 'Completed with errors',
  failed: 'Failed',
  running: 'Running',
  queued: 'Queued',
  draft: 'Draft',
}

export function LabelStatusBadge({ status }: { status: string }) {
  return <Badge variant={LABEL_STATUS_VARIANTS[status] ?? 'secondary'}>{LABEL_STATUS_TEXT[status] ?? status}</Badge>
}

export function RunStatusBadge({ status }: { status: string }) {
  return <Badge variant={RUN_STATUS_VARIANTS[status] ?? 'secondary'}>{RUN_STATUS_TEXT[status] ?? status}</Badge>
}
