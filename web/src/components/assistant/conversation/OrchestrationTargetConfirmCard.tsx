import type { Asset } from '../../../types/ops'

type Props = {
  prompt: string
  assets: Asset[]
  reason: string
  confidence: 'high' | 'medium' | 'low'
  maxConcurrency: number
  resolving?: boolean
  onStart: () => void
  onCancel: () => void
}

const confidenceLabel = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
}

export function OrchestrationTargetConfirmCard({
  prompt,
  assets,
  reason,
  confidence,
  maxConcurrency,
  resolving = false,
  onStart,
  onCancel,
}: Props) {
  return (
    <section className="relative z-10 mx-4 mt-4 rounded-2xl border border-ops-cyan/25 bg-ops-panel/70 p-4 shadow-[0_18px_48px_rgb(var(--ops-bg)/0.36)] backdrop-blur-md">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="relative flex h-2.5 w-2.5 shrink-0">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-ops-cyan opacity-25" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-ops-cyan shadow-glow" />
            </span>
            <h3 className="text-[13px] font-black tracking-[0.08em] text-ops-cyan">Confirm Multi-Asset Run</h3>
          </div>
          <p className="mt-2 line-clamp-2 text-[13px] leading-5 text-ops-text">{prompt}</p>
        </div>
        <span className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-ops-cyan/30 bg-ops-cyan/10 px-2 py-1 text-[10px] font-bold tracking-[0.1em] text-ops-cyan">
          <span className="h-1.5 w-1.5 rounded-full bg-ops-cyan" />
          {confidenceLabel[confidence]}
        </span>
      </div>

      <div className="mt-3 rounded-xl border border-ops-border/30 bg-ops-deep/70 p-3 text-[12px] leading-5 text-ops-muted shadow-inner">
        {reason || '目标资产已根据提示词解析，请确认后再执行。'}
      </div>

      <div className="mt-3 max-h-52 overflow-auto rounded-xl border border-ops-border/25 bg-ops-deep/45">
        {assets.length > 0 ? (
          assets.map((asset) => (
            <div key={asset.id} className="grid grid-cols-[minmax(0,1fr)_auto] gap-3 border-b border-ops-border/15 px-3 py-2.5 last:border-b-0">
              <div className="min-w-0">
                <div className="truncate text-[13px] font-bold text-ops-text">{asset.name}</div>
                <div className="mt-1 truncate font-mono text-[11px] text-ops-muted/75">
                  {asset.assetType} · {asset.host || 'local'} · {asset.tags.join(', ') || 'no tags'}
                </div>
              </div>
              <span className="font-mono text-[11px] text-ops-muted/60">#{asset.id}</span>
            </div>
          ))
        ) : (
          <div className="px-3 py-4 text-[12px] text-ops-muted">No target assets resolved.</div>
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <div className="font-mono text-[11px] text-ops-muted">
          Targets {assets.length} · Concurrency {maxConcurrency}
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="rounded-xl border border-ops-border/30 bg-ops-deep/70 px-3 py-2 text-[11px] font-bold text-ops-muted transition-all duration-200 hover:border-ops-danger/35 hover:text-ops-danger active:scale-95"
            onClick={onCancel}
          >
            Cancel
          </button>
          <button
            type="button"
            className="rounded-xl border border-ops-cyan/45 bg-ops-cyan/15 px-3 py-2 text-[11px] font-black tracking-[0.08em] text-ops-cyan shadow-glow transition-all duration-200 hover:bg-ops-cyan/25 active:scale-95 disabled:cursor-not-allowed disabled:opacity-45"
            onClick={onStart}
            disabled={assets.length === 0 || resolving}
          >
            {resolving ? 'Resolving...' : 'Start Run'}
          </button>
        </div>
      </div>
    </section>
  )
}
