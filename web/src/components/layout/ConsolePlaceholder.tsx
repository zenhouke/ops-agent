type ConsolePlaceholderProps = {
  error: string | null
  emptyMessage: string
}

const className = 'flex h-full items-center justify-center border-x border-ops-border/40 bg-ops-deep'

export function ConsolePlaceholder({ error, emptyMessage }: ConsolePlaceholderProps) {
  if (error) {
    return (
      <section className={className}>
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,rgb(var(--ops-danger)/0.05),transparent_80%)] pointer-events-none" />
        <p className="text-ops-danger font-bold tracking-[0.1em] text-[11px] shadow-glow">{error}</p>
      </section>
    )
  }
  return (
    <section className={className}>
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,rgb(var(--ops-cyan)/0.04),transparent_80%)] pointer-events-none" />
      <div className="flex flex-col items-center gap-4">
        <div className="h-12 w-12 rounded-2xl border border-ops-border/20 bg-ops-panel/40 flex items-center justify-center text-ops-muted/30">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /><path d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" /></svg>
        </div>
        <p className="text-ops-muted/40 font-bold tracking-[0.1em] text-[10px]">{emptyMessage}</p>
      </div>
    </section>
  )
}
