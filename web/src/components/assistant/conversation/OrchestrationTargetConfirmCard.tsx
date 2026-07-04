import type { Asset, OrchestrationTargetPreparation, OrchestrationTargetPreparationStatus } from '../../../types/ops'

type Props = {
  prompt: string
  assets: Asset[]
  preparations: OrchestrationTargetPreparation[]
  reason: string
  confidence: 'high' | 'medium' | 'low'
  maxConcurrency: number
  resolving?: boolean
  running?: boolean
  onStart: () => void
  onCancel: () => void
}

const confidenceLabel = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
}

const statusTone: Record<OrchestrationTargetPreparationStatus, string> = {
  ready: 'border-ops-green/30 bg-ops-green/10 text-ops-green',
  needs_terminal: 'border-ops-warning/35 bg-ops-warning/10 text-ops-warning',
  unavailable: 'border-ops-danger/35 bg-ops-danger/10 text-ops-danger',
}

const statusLabel: Record<OrchestrationTargetPreparationStatus, string> = {
  ready: 'Ready',
  needs_terminal: 'Will Open',
  unavailable: 'Unavailable',
}

export function OrchestrationTargetConfirmCard({
  prompt,
  assets,
  preparations,
  reason,
  confidence,
  maxConcurrency,
  resolving = false,
  running = false,
  onStart,
  onCancel,
}: Props) {
  const readyCount = preparations.filter((item) => item.status === 'ready').length
  const needsTerminalCount = preparations.filter((item) => item.status === 'needs_terminal').length
  const unavailableCount = preparations.filter((item) => item.status === 'unavailable').length
  const runnableCount = readyCount + needsTerminalCount
  const busy = resolving || running
  const assetById = new Map(assets.map((asset) => [asset.id, asset]))

  return (
    <section className="relative z-10 mx-4 mt-4 rounded-xl border border-ops-green/20 bg-ops-panel/55 p-4 backdrop-blur-md">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 shrink-0 rounded-full bg-ops-green animate-pulse" />
            <h3 className="text-[12px] font-bold tracking-[0.06em] text-ops-green">Confirm Multi-Asset Run</h3>
          </div>
          <p className="mt-2 line-clamp-2 text-[13px] leading-5 text-ops-text">{prompt}</p>
        </div>
        <span className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-ops-green/30 bg-ops-green/10 px-2 py-1 text-[10px] font-bold tracking-[0.1em] text-ops-green">
          <span className="h-1.5 w-1.5 rounded-full bg-ops-green" />
          {confidenceLabel[confidence]}
        </span>
      </div>

      <div className="mt-3 rounded-xl border border-ops-border/30 bg-ops-deep/70 p-3 text-[12px] leading-5 text-ops-muted shadow-inner">
        {reason || '目标资产已根据提示词解析，请确认后再执行。'}
      </div>

      <div className="mt-3 max-h-52 overflow-auto rounded-xl border border-ops-border/25 bg-ops-deep/45">
        {preparations.length > 0 ? (
          preparations.map((preparation) => {
            const asset = assetById.get(preparation.assetId)
            const status = preparation.status
            return (
            <div key={preparation.assetId} className="grid grid-cols-[minmax(0,1fr)_auto] gap-3 border-b border-ops-border/15 px-3 py-2.5 last:border-b-0">
              <div className="min-w-0">
                <div className="flex min-w-0 items-center gap-2">
                  <div className="truncate text-[13px] font-bold text-ops-text">{asset?.name ?? preparation.assetName}</div>
                  <span className={`inline-flex shrink-0 items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] font-bold ${statusTone[status]}`}>
                    {statusLabel[status]}
                  </span>
                </div>
                <div className="mt-1 truncate font-mono text-[11px] text-ops-muted/75">
                  {asset ? `${asset.assetType} · ${asset.host || 'local'} · ${asset.tags.join(', ') || 'no tags'}` : 'asset metadata will refresh after bootstrap'}
                </div>
                {preparation.reason ? (
                  <div className="mt-1 truncate text-[11px] text-ops-muted/60">{preparation.reason}</div>
                ) : null}
              </div>
              <div className="flex flex-col items-end gap-1">
                <span className="font-mono text-[11px] text-ops-muted/60">#{preparation.assetId}</span>
                {preparation.terminalId ? (
                  <span className="max-w-[120px] truncate font-mono text-[10px] text-ops-green/70">{preparation.terminalId.slice(0, 8)}</span>
                ) : null}
              </div>
            </div>
            )
          })
        ) : (
          <div className="px-3 py-4 text-[12px] text-ops-muted">No target assets resolved.</div>
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <div className="font-mono text-[11px] text-ops-muted">
          Targets {preparations.length} · Ready {readyCount} · Open {needsTerminalCount} · Blocked {unavailableCount} · Concurrency {maxConcurrency}
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="rounded-xl border border-ops-border/30 bg-ops-deep/70 px-3 py-2 text-[11px] font-bold text-ops-muted transition-all duration-200 hover:border-ops-danger/35 hover:text-ops-danger active:scale-95 disabled:cursor-not-allowed disabled:opacity-45"
            onClick={onCancel}
            disabled={busy}
          >
            Cancel
          </button>
          <button
            type="button"
            className="rounded-lg border border-ops-green/35 bg-ops-green/12 px-3 py-2 text-[11px] font-bold tracking-[0.06em] text-ops-green transition-all duration-200 hover:bg-ops-green/20 active:scale-95 disabled:cursor-not-allowed disabled:opacity-45"
            onClick={onStart}
            disabled={runnableCount === 0 || busy}
          >
            {resolving ? 'Resolving...' : running ? 'Starting...' : 'Start Run'}
          </button>
        </div>
      </div>
    </section>
  )
}
