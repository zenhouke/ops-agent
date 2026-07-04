import type { OrchestrationChildStatus, OrchestrationSnapshot, OrchestrationStatus } from '../../../types/ops'
import { getApprovalKeys, isApprovalSettlingEvent } from '../../../utils/approvalState'

type ApprovalCardItem = {
  eventId: string
  runtimeId: string
  approvalToken: string
  command: string
}

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
  return 'border-ops-green/30 bg-ops-green/10 text-ops-green'
}

function pendingApprovalCards(child: OrchestrationSnapshot['children'][number]): ApprovalCardItem[] {
  if (!child.runtimeId) {
    return []
  }
  const settledApprovalKeys = new Set<string>()
  const approvals: ApprovalCardItem[] = []
  for (let index = child.events.length - 1; index >= 0; index -= 1) {
    const event = child.events[index]
    if (event.kind !== 'message_update') {
      if (isApprovalSettlingEvent(event)) {
        getApprovalKeys(event).forEach((key) => settledApprovalKeys.add(key))
      }
      continue
    }
    const approvalKeys = getApprovalKeys(event)
    if (approvalKeys.length > 0 && isApprovalSettlingEvent(event)) {
      approvalKeys.forEach((key) => settledApprovalKeys.add(key))
      continue
    }
    const message = event as any
    const approvalToken = message.toolCall?.approvalToken ?? null
    if (message.type !== 'ask' || !approvalToken || approvalKeys.some((key) => settledApprovalKeys.has(key))) {
      continue
    }
    approvals.push({
      eventId: String(message.id ?? event.id ?? approvalKeys[0] ?? index),
      runtimeId: child.runtimeId,
      approvalToken,
      command: message.toolCall?.command ?? message.toolCall?.displayText ?? 'Command approval required',
    })
  }
  return approvals.reverse()
}

export function OrchestrationCard({ snapshot, onCancel, onApprove, onReject }: Props) {
  const completed = snapshot.children.filter((child) => child.status === 'completed').length
  const failed = snapshot.children.filter((child) => child.status === 'failed').length
  const needsApproval = snapshot.children.filter((child) => child.status === 'needs_approval').length

  return (
    <section className="relative z-10 mx-4 mt-4 rounded-xl border border-ops-border/20 bg-ops-panel/50 p-4 backdrop-blur-md">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 shrink-0 rounded-full bg-ops-green animate-pulse" />
            <h3 className="text-[12px] font-bold tracking-[0.06em] text-ops-green">Multi-Asset Run</h3>
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
              {pendingApprovalCards(child).map((approval) => (
                <div key={`${approval.runtimeId}-${approval.eventId}`} className="rounded-xl border border-ops-warning/25 bg-ops-warning/10 p-3">
                  <div className="text-[10px] font-bold tracking-[0.1em] text-ops-warning">Approval Required</div>
                  <pre className="mt-2 overflow-auto rounded-lg border border-ops-warning/20 bg-black/55 p-2 font-mono text-[11px] text-ops-text shadow-inner">{approval.command}</pre>
                  <div className="mt-2 flex justify-end gap-2">
                    <button
                      type="button"
                      className="rounded-lg border border-ops-border/30 bg-ops-deep/70 px-2.5 py-1.5 text-[10px] font-bold text-ops-muted transition-all duration-200 hover:border-ops-danger/35 hover:text-ops-danger active:scale-95"
                      onClick={() => onReject?.(approval.runtimeId, approval.approvalToken)}
                    >
                      Reject
                    </button>
                    <button
                      type="button"
                      className="rounded-lg border border-ops-warning/40 bg-ops-warning/15 px-2.5 py-1.5 text-[10px] font-black text-ops-warning transition-all duration-200 hover:bg-ops-warning/20 active:scale-95"
                      onClick={() => onApprove?.(approval.runtimeId, approval.approvalToken)}
                    >
                      Approve
                    </button>
                  </div>
                </div>
              ))}
              {child.errorMessage ? <div className="rounded-lg border border-ops-danger/20 bg-ops-danger/10 p-2 text-ops-danger">{child.errorMessage}</div> : null}
              {child.summary ? <div className="rounded-lg border border-ops-border/20 bg-ops-panel/35 p-2">{child.summary}</div> : null}
              {child.events.slice(-4).map((event, eventIndex) => (
                <pre key={`${event.id}-${eventIndex}`} className="max-h-32 overflow-auto rounded-lg border border-ops-border/20 bg-black/60 p-2 font-mono text-[11px] text-ops-muted shadow-inner">
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
