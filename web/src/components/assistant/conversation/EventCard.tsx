import { useState } from 'react'
import { useAppearance } from '../../../hooks/useAppearance'
import type { EventItem } from '../../../types/ops'
import { AssistantMessageContent } from './AssistantMessageContent'

type EventCardProps = {
  event: EventItem
  pendingApprovalRuntimeId: string | null
  onApprove?: (allowPrefix?: string) => void
  onReject?: () => void
  onTerminalRequestDecision?: (input: { runtimeId: string; requestId: string; approvalToken: string; approved: boolean }) => Promise<void>
  settledTerminalRequestIds?: Set<string>
}

function eventValue(event: EventItem, key: string): string | undefined {
  const value = (event as unknown as Record<string, unknown>)[key]
  return typeof value === 'string' ? value : undefined
}

export function EventCard({ event, onTerminalRequestDecision, settledTerminalRequestIds }: EventCardProps) {
  const { t } = useAppearance()
  const [submittingTerminalDecision, setSubmittingTerminalDecision] = useState(false)

  if (event.kind === 'error') {
    return (
      <div className="my-1 rounded-[5px] border border-ops-danger/40 bg-ops-danger/[0.07] p-3 shadow-inner" role="alert">
        <div className="mb-2 flex items-center gap-2 text-[10px] font-bold tracking-[0.1em] text-ops-danger">
          <span className="h-1.5 w-1.5 rounded-full bg-ops-danger" />
          {t('conversation.systemError')}
        </div>
        <p className="m-0 whitespace-pre-wrap font-mono text-xs leading-relaxed text-ops-text/90">{event.text}</p>
      </div>
    )
  }

  if (event.kind === 'user') {
    return (
      <section className="border-b border-ops-border/20 pb-3">
        <div className="mb-1.5 flex items-center gap-2 text-[10px] font-semibold text-ops-cyan">
          <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2.4" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="m8 12 2.5 2.5L16 9" /></svg>
          任务目标
        </div>
        <p className="m-0 whitespace-pre-wrap text-[14px] font-medium leading-6 text-ops-text">{event.text}</p>
      </section>
    )
  }

  if (event.kind === 'terminal_session_request') {
    const runtimeId = event.runtimeId
    const requestId = event.requestId ?? undefined
    const approvalToken = event.approvalToken ?? undefined
    const assetName = event.assetName ?? `asset-${event.assetId ?? ''}`
    const reason = event.reason ?? 'Agent requested terminal access.'
    const settled = Boolean(requestId && settledTerminalRequestIds?.has(requestId))
    if (settled) return null
    const canDecide = Boolean(runtimeId && requestId && approvalToken && onTerminalRequestDecision && !submittingTerminalDecision)
    return (
      <div className="relative my-2 overflow-hidden rounded-[5px] border border-ops-warning/40 bg-ops-warning/[0.07] p-3 shadow-inner">
        <div className="absolute bottom-0 left-0 top-0 w-0.5 bg-ops-warning/80" />
        <div className="mb-2 flex items-center gap-2 text-ops-warning">
          <span className="h-1.5 w-1.5 rounded-full bg-ops-warning" />
          <span className="text-[10px] font-bold tracking-[0.1em]">Terminal access request</span>
        </div>
        <p className="m-0 text-[12px] font-semibold text-ops-text">{assetName}</p>
        <p className="mt-1.5 whitespace-pre-wrap text-[11px] leading-relaxed text-ops-muted">{reason}</p>
        {settled ? <p className="mt-3 text-xs text-ops-muted">This request has been decided.</p> : null}
        {canDecide ? (
          <div className="mt-3 flex gap-2 border-t border-ops-warning/15 pt-3">
            <button
              type="button"
              className="rounded-[4px] border border-ops-green/30 bg-ops-green/10 px-3 py-1.5 text-[10px] font-bold tracking-[0.08em] text-ops-green transition-all duration-200 hover:bg-ops-green/20 active:scale-95"
              disabled={!canDecide}
              onClick={() => {
                if (!runtimeId || !requestId || !approvalToken || !onTerminalRequestDecision) return
                setSubmittingTerminalDecision(true)
                void onTerminalRequestDecision({ runtimeId, requestId, approvalToken, approved: true }).finally(() => {
                  setSubmittingTerminalDecision(false)
                })
              }}
            >
              {submittingTerminalDecision ? 'Submitting' : 'Allow'}
            </button>
            <button
              type="button"
              className="rounded-[4px] border border-ops-danger/30 bg-ops-danger/10 px-3 py-1.5 text-[10px] font-bold tracking-[0.08em] text-ops-danger transition-all duration-200 hover:bg-ops-danger/20 active:scale-95"
              disabled={!canDecide}
              onClick={() => {
                if (!runtimeId || !requestId || !approvalToken || !onTerminalRequestDecision) return
                setSubmittingTerminalDecision(true)
                void onTerminalRequestDecision({ runtimeId, requestId, approvalToken, approved: false }).finally(() => {
                  setSubmittingTerminalDecision(false)
                })
              }}
            >
              Reject
            </button>
          </div>
        ) : null}
      </div>
    )
  }

  if (event.kind === 'terminal_session_opened') {
    return null
  }

  if (event.kind === 'terminal_session_rejected') {
    return null
  }

  if (event.kind === 'terminal_authorization_revoked') {
    return null
  }

  if ((event.kind === 'approval_required' || event.kind === 'approval_decision') && event.status === 'rejected') {
    return (
      <div className="my-2 rounded-[5px] border border-ops-danger/40 bg-ops-danger/[0.07] p-3 shadow-inner">
        <div className="mb-2 flex items-center gap-2 text-ops-danger">
          <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><circle cx="12" cy="12" r="10" /><line x1="15" y1="9" x2="9" y2="15" /><line x1="9" y1="9" x2="15" y2="15" /></svg>
          <span className="text-[10px] font-bold tracking-[0.1em]">{t('conversation.accessDenied')}</span>
        </div>
        <p className="m-0 whitespace-pre-wrap rounded-[4px] border border-ops-danger/20 bg-ops-deep/80 p-2.5 font-mono text-[12px] leading-relaxed text-ops-text/80 shadow-inner">{event.command || event.text}</p>
      </div>
    )
  }

  if (event.kind === 'final') {
    if (!event.text) return null
    return (
      <section className="relative my-2 overflow-hidden rounded-[5px] border border-ops-green/30 bg-ops-panel/40 p-3 shadow-inner backdrop-blur-sm" role="status" aria-live="polite">
        <div className="pointer-events-none absolute bottom-0 left-0 top-0 w-0.5 bg-ops-green/75" aria-hidden="true" />
        <div className="mb-2.5 flex items-center justify-between gap-3 border-b border-ops-border/20 pb-2.5">
          <div className="flex items-center gap-2.5">
            <span className="flex h-7 w-7 items-center justify-center rounded-[4px] border border-ops-green/30 bg-ops-green/10 text-ops-green" aria-hidden="true">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
            </span>
            <div>
              <div className="text-[10px] font-bold tracking-[0.1em] text-ops-green">{t('conversation.runComplete')}</div>
              <div className="mt-0.5 text-[12px] text-ops-muted/68">{t('conversation.finalSummary')}</div>
            </div>
          </div>
          <span className="rounded-[4px] border border-ops-green/25 bg-ops-green/8 px-2 py-0.5 text-[9px] font-bold tracking-[0.08em] text-ops-green">{t('conversation.finished')}</span>
        </div>
        <AssistantMessageContent content={event.text} />
      </section>
    )
  }

  return null
}
