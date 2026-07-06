interface ProgressProps {
  value: number
}

export function Progress({ value }: ProgressProps) {
  const safe = Math.max(0, Math.min(100, value))
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
      <div
        className="h-full rounded-full bg-primary transition-all"
        style={{ width: `${safe}%` }}
      />
    </div>
  )
}
