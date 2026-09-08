import { useId } from 'react'

import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

export const REQUIRED_FIELD_CLASS = 'border-amber-200 bg-amber-50/70 focus-visible:ring-amber-300'

export function Field({
  label,
  value,
  onChange,
  required,
  className,
  type = 'text',
}: {
  label: string
  value: string
  onChange: (value: string) => void
  required?: boolean
  className?: string
  type?: string
}) {
  const id = useId()
  return (
    <div className={`space-y-2 ${className ?? ''}`}>
      <Label htmlFor={id}>
        {label}
        {required && <span className="ml-0.5 text-amber-600">*</span>}
      </Label>
      <Input
        id={id}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        className={required ? REQUIRED_FIELD_CLASS : undefined}
      />
    </div>
  )
}
