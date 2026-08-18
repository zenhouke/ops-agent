type EmptyStateProps = {
  title: string
  description: string
  targetLabel?: string
  targetMeta?: string
  suggestions?: string[]
  onSelectSuggestion?: (suggestion: string) => void
}

export function EmptyState({ title, description, targetLabel, targetMeta, suggestions = [], onSelectSuggestion }: EmptyStateProps) {
  return (
    <div className="flex min-h-full items-center justify-center px-6 py-10" role="region" aria-label={title}>
      <div className="w-full max-w-[680px] overflow-hidden rounded-xl border border-ops-border/35 bg-ops-panel/45 shadow-[0_24px_80px_rgb(0_0_0/0.18)]">
        <div className="flex items-center gap-3 border-b border-ops-border/25 bg-ops-deep/55 px-5 py-4">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-ops-cyan/25 bg-ops-cyan/10 text-ops-cyan" aria-hidden="true">
            <svg viewBox="0 0 24 24" className="h-4 w-4 fill-none stroke-current" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 17 10 11 4 5" /><path d="M12 19h8" /></svg>
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="text-[13px] font-semibold text-ops-text">{title}</h3>
            <p className="mt-0.5 text-[11px] leading-5 text-ops-muted/75">{description}</p>
          </div>
          {targetLabel ? (
            <div className="hidden min-w-0 items-center gap-2 rounded-md border border-ops-green/20 bg-ops-green/5 px-2.5 py-1.5 sm:flex">
              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-ops-green shadow-[0_0_8px_rgb(var(--ops-green)/0.55)]" />
              <span className="max-w-[120px] truncate text-[10px] font-semibold text-ops-text/85">{targetLabel}</span>
              {targetMeta ? <span className="max-w-[120px] truncate font-mono text-[9px] text-ops-muted/55">{targetMeta}</span> : null}
            </div>
          ) : null}
        </div>
        {suggestions.length > 0 ? (
          <div className="grid gap-2 p-3 sm:grid-cols-3">
            {suggestions.map((suggestion, index) => (
              <button
                key={suggestion}
                type="button"
                className="group flex min-h-[76px] flex-col justify-between rounded-lg border border-ops-border/25 bg-ops-bg/45 p-3 text-left transition hover:border-ops-cyan/35 hover:bg-ops-cyan/5 active:scale-[0.99]"
                onClick={() => onSelectSuggestion?.(suggestion)}
              >
                <span className="font-mono text-[9px] text-ops-cyan/70">0{index + 1}</span>
                <span className="text-[11px] font-medium leading-4 text-ops-text/78 transition group-hover:text-ops-text">{suggestion}</span>
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  )
}
