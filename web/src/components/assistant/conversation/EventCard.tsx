import { useState } from 'react'
import { motion } from 'framer-motion'
import { useAppearance } from '../../../hooks/useAppearance'
import type { EventItem } from '../../../types/ops'
import { AssistantMessageContent } from './AssistantMessageContent'
import { cardMotionProps } from '../../motion-primitives'

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
      <motion.div {...cardMotionProps} className="my-1 rounded-xl border border-ops-danger/25 bg-ops-danger/8 p-3.5" role="alert">
        <div className="mb-2 flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.12em] text-ops-danger">
          <span className="h-1.5 w-1.5 rounded-full bg-ops-danger" />
          {t('conversation.systemError')}
        </div>
        <p className="m-0 whitespace-pre-wrap font-mono text-xs leading-relaxed text-ops-text/85">{event.text}</p>
      </motion.div>
    )
  }

  if (event.kind === 'user') {
    return (
      <motion.div {...cardMotionProps} className="flex justify-end">
        <article className="max-w-[78%] rounded-2xl rounded-br-sm border border-ops-green/20 bg-ops-green/8 px-4 py-3 shadow-sm">
          <p className="m-0 whitespace-pre-wrap text-[13.5px] font-medium leading-7 text-ops-text/95">{event.text}</p>
        </article>
      </motion.div>
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
      <motion.div {...cardMotionProps} className="my-2 rounded-xl border border-ops-warning/25 bg-ops-warning/8 p-4">
        <div className="mb-3 flex items-center gap-2 text-ops-warning">
          <span className="h-1.5 w-1.5 rounded-full bg-ops-warning" />
          <span className="text-[10px] font-bold uppercase tracking-[0.12em]">{t('conversation.terminalRequest')}</span>
        </div>
        <p className="m-0 text-sm font-semibold text-ops-text">{assetName}</p>
        <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-ops-muted">{reason}</p>
        {settled ? <p className="mt-3 text-xs text-ops-muted">{t('conversation.terminalRequestDecided')}</p> : null}
        {canDecide ? (
          <div className="mt-4 flex gap-2">
            <button
              type="button"
              className="rounded-xl border border-ops-green/30 bg-ops-green/10 px-3 py-2 text-[10px] font-black uppercase tracking-[0.14em] text-ops-green transition-all duration-200 hover:bg-ops-green/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ops-green/35 active:scale-95 disabled:cursor-not-allowed disabled:opacity-45 disabled:active:scale-100"
              disabled={!canDecide}
              onClick={() => {
                if (!runtimeId || !requestId || !approvalToken || !onTerminalRequestDecision) return
                setSubmittingTerminalDecision(true)
                void onTerminalRequestDecision({ runtimeId, requestId, approvalToken, approved: true }).finally(() => {
                  setSubmittingTerminalDecision(false)
                })
              }}
            >
              {submittingTerminalDecision ? t('conversation.submitting') : t('conversation.allow')}
            </button>
            <button
              type="button"
              className="rounded-xl border border-ops-danger/30 bg-ops-danger/10 px-3 py-2 text-[10px] font-black uppercase tracking-[0.14em] text-ops-danger transition-all duration-200 hover:bg-ops-danger/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ops-danger/35 active:scale-95 disabled:cursor-not-allowed disabled:opacity-45 disabled:active:scale-100"
              disabled={!canDecide}
              onClick={() => {
                if (!runtimeId || !requestId || !approvalToken || !onTerminalRequestDecision) return
                setSubmittingTerminalDecision(true)
                void onTerminalRequestDecision({ runtimeId, requestId, approvalToken, approved: false }).finally(() => {
                  setSubmittingTerminalDecision(false)
                })
              }}
            >
              {t('conversation.reject')}
            </button>
          </div>
        ) : null}
      </motion.div>
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
      <motion.div {...cardMotionProps} className="my-2 rounded-xl border border-ops-danger/25 bg-ops-danger/8 p-4">
        <div className="mb-3 flex items-center gap-2 text-ops-danger">
          <svg aria-hidden="true" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><circle cx="12" cy="12" r="10" /><line x1="15" y1="9" x2="9" y2="15" /><line x1="9" y1="9" x2="15" y2="15" /></svg>
          <span className="text-[10px] font-bold uppercase tracking-[0.12em]">{t('conversation.accessDenied')}</span>
        </div>
        <p className="m-0 whitespace-pre-wrap rounded-lg border border-ops-danger/15 bg-ops-deep/40 p-3 font-mono text-[12px] leading-relaxed text-ops-text/80">{event.command || event.text}</p>
      </motion.div>
    )
  }

  if (event.kind === 'final') {
    if (!event.text) return null
    return (
      <motion.section {...cardMotionProps} className="relative my-2 overflow-hidden rounded-2xl border border-ops-green/20 bg-ops-panel/50 p-4" role="status" aria-live="polite">
        <div className="mb-3 flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.12em] text-ops-green">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
          {t('conversation.runComplete')}
        </div>
        <AssistantMessageContent content={event.text} />
      </motion.section>
    )
  }

  return null
}
