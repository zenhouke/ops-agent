import { useState } from 'react'
import { useAppearance } from '../../../hooks/useAppearance'
import type { EventItem } from '../../../types/ops'
import { AssistantMessageContent } from './AssistantMessageContent'

type EventCardProps = {
  event: EventItem
  pendingApprovalRuntimeId: string | null
  onApprove?: (allowPrefix?: string, guidance?: string) => void
  onReject?: (guidance?: string) => void
  onTerminalRequestDecision?: (input: { runtimeId: string; requestId: string; approvalToken: string; approved: boolean }) => Promise<void>
  settledTerminalRequestIds?: Set<string>
  onEditRun?: (eventId: string, prompt: string) => Promise<void>
  onRetryRun?: (eventId: string, prompt: string) => Promise<void>
  actionsDisabled?: boolean
}

function eventValue(event: EventItem, key: string): string | undefined {
  const value = (event as unknown as Record<string, unknown>)[key]
  return typeof value === 'string' ? value : undefined
}

export function EventCard({ event, onTerminalRequestDecision, settledTerminalRequestIds, onEditRun, onRetryRun, actionsDisabled = false }: EventCardProps) {
  const { t } = useAppearance()
  const [submittingTerminalDecision, setSubmittingTerminalDecision] = useState(false)
  const [editingPrompt, setEditingPrompt] = useState(false)
  const [editedPrompt, setEditedPrompt] = useState('')
  const [actionPending, setActionPending] = useState(false)

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

  if (event.kind === 'conversation_branch') {
    return (
      <div className="my-1 flex items-center gap-2 text-[10px] text-ops-muted/60" role="status">
        <span className="h-px flex-1 bg-ops-border/25" />
        <span>从历史节点创建的分支</span>
        <span className="h-px flex-1 bg-ops-border/25" />
      </div>
    )
  }

  if (event.kind === 'user') {
    const prompt = event.text ?? ''
    return (
      <section className="border-b border-ops-border/20 pb-3">
        <div className="mb-1.5 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-[10px] font-semibold text-ops-cyan">
            <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2.4" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="m8 12 2.5 2.5L16 9" /></svg>
            {event.runtimeMessage
              ? event.deliveryStatus === 'queued'
                ? actionsDisabled ? '补充指令 · 等待应用' : '补充指令 · 已应用'
                : '补充回复'
              : '任务目标'}
            {eventValue(event, 'mode') === 'incident' ? <span className="rounded border border-ops-danger/35 bg-ops-danger/10 px-1.5 py-0.5 text-[9px] text-ops-danger">事故模式</span> : null}
          </div>
          {onEditRun || onRetryRun ? (
            <div className="flex items-center gap-1 text-[10px]">
              {onEditRun ? <button type="button" className="rounded px-1.5 py-0.5 text-ops-muted hover:bg-ops-panel hover:text-ops-cyan disabled:opacity-40" disabled={actionsDisabled || actionPending} onClick={() => { setEditedPrompt(prompt); setEditingPrompt(true) }}>编辑</button> : null}
              {onRetryRun ? <button type="button" className="rounded px-1.5 py-0.5 text-ops-muted hover:bg-ops-panel hover:text-ops-cyan disabled:opacity-40" disabled={actionsDisabled || actionPending} onClick={() => { setActionPending(true); void onRetryRun(event.id, prompt).finally(() => setActionPending(false)) }}>重试</button> : null}
            </div>
          ) : null}
        </div>
        {editingPrompt ? (
          <div className="space-y-2">
            <textarea className="min-h-20 w-full resize-y rounded border border-ops-border/50 bg-ops-deep p-2 text-sm leading-6 text-ops-text outline-none focus:border-ops-cyan/60" value={editedPrompt} onChange={(inputEvent) => setEditedPrompt(inputEvent.target.value)} aria-label="编辑任务目标" />
            <div className="flex justify-end gap-2">
              <button type="button" className="rounded px-2 py-1 text-[10px] text-ops-muted hover:text-ops-text" onClick={() => setEditingPrompt(false)}>取消</button>
              <button type="button" className="rounded border border-ops-cyan/35 bg-ops-cyan/10 px-2 py-1 text-[10px] font-semibold text-ops-cyan disabled:opacity-40" disabled={!editedPrompt.trim() || actionPending} onClick={() => { if (!editedPrompt.trim() || !onEditRun) return; setEditingPrompt(false); setActionPending(true); void onEditRun(event.id, editedPrompt.trim()).finally(() => setActionPending(false)) }}>保存</button>
            </div>
          </div>
        ) : <p className="m-0 whitespace-pre-wrap text-[14px] font-medium leading-6 text-ops-text">{prompt}</p>}
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
          <span className="text-[10px] font-bold tracking-[0.1em]">
            {event.scopeExpansionRequired ? '扩展多资产任务范围' : '终端访问请求'}
          </span>
        </div>
        <p className="m-0 text-[12px] font-semibold text-ops-text">{assetName}</p>
        <p className="mt-1.5 whitespace-pre-wrap text-[11px] leading-relaxed text-ops-muted">{reason}</p>
        {event.scopeExpansionRequired ? (
          <p className="mt-2 rounded border border-ops-warning/20 bg-ops-deep/35 px-2 py-1.5 text-[10px] leading-relaxed text-ops-warning/90">
            允许后，该资产会加入本对话白名单，并可用于本次多资产诊断与拓扑采集。
          </p>
        ) : null}
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
              {submittingTerminalDecision ? '提交中' : event.scopeExpansionRequired ? '加入范围并连接' : '允许连接'}
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
