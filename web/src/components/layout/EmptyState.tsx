type EmptyStateProps = {
  title: string
  description: string
}

export function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <div className="relative flex min-h-full flex-col items-center justify-center overflow-hidden rounded-[28px] border border-ops-border/15 bg-[radial-gradient(circle_at_50%_16%,rgb(var(--ops-green)/0.13),transparent_32%),linear-gradient(180deg,rgb(var(--ops-panel)/0.46),rgb(var(--ops-deep)/0.68))] p-8 text-center" role="status">
      <div className="pointer-events-none absolute inset-8 rounded-full border border-ops-green/5" />
      <div className="pointer-events-none absolute h-44 w-44 rounded-full bg-ops-green/5 blur-3xl" />
      <div className="relative mb-5 flex h-16 w-16 items-center justify-center rounded-[22px] border border-ops-green/20 bg-[radial-gradient(circle_at_top,rgb(var(--ops-green)/0.24),rgb(var(--ops-panel)/0.64))] text-2xl text-ops-green shadow-[0_16px_45px_rgb(var(--ops-green)/0.16)]" aria-hidden="true">
        ✦
      </div>
      <h3 className="relative mb-2 text-sm font-black uppercase tracking-[0.14em] text-ops-text">{title}</h3>
      <p className="relative max-w-[320px] text-xs leading-6 text-ops-muted/78">{description}</p>
    </div>
  )
}
