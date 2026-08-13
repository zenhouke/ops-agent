type EmptyStateProps = {
  title: string
  description: string
}

export function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <div className="flex min-h-full items-center justify-center p-8 text-center" role="status">
      <div className="flex max-w-[340px] flex-col items-center">
        <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg border border-ops-border/55 bg-ops-panel/40 text-sm text-ops-muted" aria-hidden="true">
          _
        </div>
        <h3 className="mb-2 text-sm font-semibold tracking-wide text-ops-text">{title}</h3>
        <p className="text-xs leading-6 text-ops-muted/78">{description}</p>
      </div>
    </div>
  )
}
