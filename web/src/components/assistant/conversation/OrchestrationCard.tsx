import type { OrchestrationChildStatus, OrchestrationSnapshot, OrchestrationStatus } from '../../../types/ops'

type Props = {
  snapshot: OrchestrationSnapshot
  onCancel?: () => void
  onApprove?: (runtimeId: string, approvalToken: string | null, allowPrefix?: string) => void
  onReject?: (runtimeId: string, approvalToken: string | null) => void
}

const statusLabel: Record<OrchestrationStatus | OrchestrationChildStatus, string> = {
  pending: 'Pending',
  running: 'Running',
  needs_approval: 'Needs Approval',
  completed: 'Completed',
  partial_failed: 'Partial Failed',
  failed: 'Failed',
  cancelled: 'Cancelled',
}

function statusClass(status: string) {
  if (status === 'completed') return 'border-ops-emerald/30 bg-ops-emerald/10 text-ops-emerald'
  if (status === 'failed' || status === 'partial_failed' || status === 'cancelled') return 'border-ops-danger/30 bg-ops-danger/10 text-ops-danger'
  if (status === 'needs_approval') return 'border-ops-warning/35 bg-ops-warning/10 text-ops-warning'
  return 'border-ops-cyan/30 bg-ops-cyan/10 text-ops-cyan'
}

export function OrchestrationCard({ snapshot, onCancel, onApprove, onReject }: Props) {
  const completed = snapshot.children.filter((child) => child.status === 'completed').length
  const failed = snapshot.children.filter((child) => child.status === 'failed').length
  const needsApproval = snapshot.children.filter((child) => child.status === 'needs_approval').length

  return (
    <section className="relative z-10 mx-4 mt-4 rounded-2xl border border-ops-border/30 bg-ops-panel/55 p-4 shadow-[0_18px_48px_rgb(var(--ops-bg)/0.30)] backdrop-blur-md">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="relative flex h-2.5 w-2.5 shrink-0">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-ops-cyan opacity-25" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-ops-cyan shadow-glow" />
            </span>
            <h3 className="text-[13px] font-black tracking-[0.08em] text-ops-cyan">Multi-Asset Run</h3>
          </div>
          <p className="mt-2 text-[12px] leading-5 text-ops-muted">{snapshot.targetSelectionReason}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[10px] font-bold tracking-[0.1em] ${statusClass(snapshot.status)}`}>
            <span className="h-1.5 w-1.5 rounded-full bg-current" />
            {statusLabel[snapshot.status] ?? snapshot.status}
          </span>
          {onCancel && snapshot.status === 'running' ? (
            <button
              type="button"
              className="rounded-lg border border-ops-danger/30 bg-ops-danger/10 px-2.5 py-1.5 text-[10px] font-bold text-ops-danger transition-all duration-200 hover:bg-ops-danger/15 active:scale-95"
              onClick={onCancel}
            >
              Cancel
            </button>
          ) : null}
        </div>
      </div>

      <div className="mt-3 grid grid-cols-4 gap-2 text-[11px]">
        <Metric label="Targets" value={snapshot.children.length} tone="text-ops-text" />
        <Metric label="Done" value={completed} tone="text-ops-emerald" />
        <Metric label="Approval" value={needsApproval} tone="text-ops-warning" />
        <Metric label="Failed" value={failed} tone="text-ops-danger" />
      </div>

      <div className="mt-3 divide-y divide-ops-border/15 overflow-hidden rounded-xl border border-ops-border/25 bg-ops-deep/45">
        {snapshot.children.map((child) => (
          <details key={child.assetId} className="group">
            <summary className="grid cursor-pointer grid-cols-[minmax(0,1fr)_auto] gap-3 px-3 py-2.5 transition-colors hover:bg-ops-panel/45">
              <span className="min-w-0 truncate text-[13px] font-bold text-ops-text">{child.assetName}</span>
              <span className={`rounded-md border px-2 py-0.5 text-[10px] font-bold ${statusClass(child.status)}`}>
                {statusLabel[child.status] ?? child.status}
              </span>
            </summary>
            <div className="space-y-2 px-3 pb-3 text-[12px] text-ops-muted">
              {child.events.map((event) => {
                if (event.kind !== 'message_update') return null
                const message = event as any
                const approvalToken = message.toolCall?.approvalToken ?? null
                if (message.type !== 'ask' || !approvalToken || !child.runtimeId) return null
                const command = message.toolCall?.command ?? message.toolCall?.displayText ?? 'Command approval required'
                return (
                  <div key={`${child.runtimeId}-${message.id}`} className="rounded-xl border border-ops-warning/25 bg-ops-warning/10 p-3">
                    <div className="text-[10px] font-bold tracking-[0.1em] text-ops-warning">Approval Required</div>
                    <pre className="mt-2 overflow-auto rounded-lg border border-ops-warning/20 bg-black/55 p-2 font-mono text-[11px] text-ops-text shadow-inner">{command}</pre>
                    <div className="mt-2 flex justify-end gap-2">
                      <button
                        type="button"
                        className="rounded-lg border border-ops-border/30 bg-ops-deep/70 px-2.5 py-1.5 text-[10px] font-bold text-ops-muted transition-all duration-200 hover:border-ops-danger/35 hover:text-ops-danger active:scale-95"
                        onClick={() => onReject?.(child.runtimeId!, approvalToken)}
                      >
                        Reject
                      </button>
                      <button
                        type="button"
                        className="rounded-lg border border-ops-warning/40 bg-ops-warning/15 px-2.5 py-1.5 text-[10px] font-black text-ops-warning transition-all duration-200 hover:bg-ops-warning/20 active:scale-95"
                        onClick={() => onApprove?.(child.runtimeId!, approvalToken)}
                      >
                        Approve
                      </button>
                    </div>
                  </div>
                )
              })}
              {child.errorMessage ? <div className="rounded-lg border border-ops-danger/20 bg-ops-danger/10 p-2 text-ops-danger">{child.errorMessage}</div> : null}
              {child.summary ? <div className="rounded-lg border border-ops-border/20 bg-ops-panel/35 p-2">{child.summary}</div> : null}
              {child.events.slice(-4).map((event) => (
                <pre key={event.id} className="max-h-32 overflow-auto rounded-lg border border-ops-border/20 bg-black/60 p-2 font-mono text-[11px] text-ops-muted shadow-inner">
                  {JSON.stringify(event, null, 2)}
                </pre>
              ))}
            </div>
          </details>
        ))}
      </div>

      {snapshot.finalSummary ? (
        <div className="mt-3 rounded-xl border border-ops-border/25 bg-ops-deep/65 p-3 text-[12px] leading-5 text-ops-text shadow-inner">
          {snapshot.finalSummary}
        </div>
      ) : null}
    </section>
  )
}

function Metric({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="rounded-xl border border-ops-border/20 bg-ops-deep/55 p-2 shadow-inner">
      <div className="text-[10px] font-bold tracking-[0.1em] text-ops-muted/70">{label}</div>
      <div className={`mt-1 font-mono text-[15px] font-bold ${tone}`}>{value}</div>
    </div>
  )
}
