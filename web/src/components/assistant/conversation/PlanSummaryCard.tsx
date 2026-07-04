import { useState } from 'react'
import { useAppearance } from '../../../hooks/useAppearance'
import type { PlanEvent } from '../../../types/ops'

type PlanSummaryCardProps = {
  event: PlanEvent
  onApprovePlan?: (runtimeId: string) => void
}

export function PlanSummaryCard({ event, onApprovePlan }: PlanSummaryCardProps) {
  const { t } = useAppearance()
  const isPlanMode = event.mode === 'plan'
  const [showSteps, setShowSteps] = useState(true)
  const visibleSteps = event.steps
  const totalSteps = visibleSteps.length
  const completedSteps = visibleSteps.filter((step) => step.status === 'completed').length
  const runningStep = visibleSteps.find((step) => step.status === 'running')
  const progress = totalSteps > 0 ? Math.round((completedSteps / totalSteps) * 100) : 0
  const title = event.title?.trim()
  const displayTitle = title || (isPlanMode ? t('conversation.executionPlan') : t('conversation.taskPlan'))
  const isPlanningEmpty = event.loading && totalSteps === 0
  const isWaitingApproval = isPlanMode && event.status === 'waiting_plan_approval'
  const isFailed = event.status === 'failed'
  const statusLabel = event.loading
    ? t('conversation.planning')
    : isPlanMode
      ? (isFailed ? t('conversation.planFailed') : isWaitingApproval ? t('conversation.awaitingPlanApproval') : t('conversation.planExecuting'))
      : t('assistant.plan')

  return (
    <section className={`relative overflow-hidden border border-ops-green/15 bg-ops-deep/85 backdrop-blur-xl transition-all duration-200 ${showSteps ? 'rounded-xl' : 'rounded-full'}`}>
      <div className={showSteps ? 'p-3' : 'px-3 py-2'}>
        <div className={`flex items-center justify-between gap-2 ${showSteps ? 'flex-wrap' : ''}`}>
          <div className="min-w-0 flex flex-1 items-center gap-2">
            <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${event.loading ? 'animate-pulse bg-ops-green shadow-[0_0_16px_rgb(var(--ops-green)/0.55)]' : isPlanMode ? 'bg-ops-green' : 'bg-ops-green'}`} />
            <div className="min-w-0">
              <div className="flex min-w-0 items-center gap-2">
                <h3 className="truncate text-[11px] font-black uppercase tracking-[0.2em] text-ops-text/95">
                  {showSteps ? displayTitle : t('conversation.taskPlan')}
                </h3>
                {showSteps && event.updated ? (
                  <span className="rounded-full border border-ops-warning/30 bg-ops-warning/10 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-[0.16em] text-ops-warning">
                    {t('conversation.updated')}
                  </span>
                ) : null}
                {showSteps && isPlanMode ? (
                  <span className={`inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${isFailed ? 'border-ops-danger/35 bg-ops-danger/10 text-ops-danger' : 'border-ops-green/30 bg-ops-green/10 text-ops-green'}`}>
                    <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                      {isFailed ? <path d="m18 6-12 12M6 6l12 12" /> : <path d="M5 3v18l15-9-15-9z" />}
                    </svg>
                    {isFailed ? t('conversation.planFailed') : t('conversation.executingPlan')}
                  </span>
                ) : null}
              </div>
              <div className={`flex items-center gap-2 text-[10px] text-ops-muted ${showSteps ? 'mt-1' : ''}`}>
                <span className={event.loading || isPlanMode ? (isFailed ? 'text-ops-danger' : isWaitingApproval ? 'text-ops-warning' : 'text-ops-green') : undefined}>{statusLabel}</span>
                {totalSteps > 0 ? <span className="tabular-nums">{completedSteps}/{totalSteps}</span> : null}
                {showSteps && typeof event.version === 'number' && event.version > 0 ? (
                  <span className="rounded-md bg-ops-panel/55 px-1.5 py-0.5 font-mono text-[10px] text-ops-muted/90">v{event.version}</span>
                ) : null}
              </div>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {showSteps && isWaitingApproval && !isFailed ? (
              <button
                type="button"
                className="button-mini h-7 gap-1.5 border-ops-warning/30 bg-ops-warning/10 px-2 text-[10px] uppercase tracking-[0.14em] text-ops-warning hover:bg-ops-warning/15 disabled:cursor-not-allowed disabled:opacity-45"
                disabled={!event.runtimeId || !onApprovePlan}
                onClick={() => {
                  if (event.runtimeId) {
                    onApprovePlan?.(event.runtimeId)
                  }
                }}
              >
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M5 3v18l15-9-15-9z" />
                </svg>
                {t('conversation.executePlan')}
              </button>
            ) : null}
            {showSteps && totalSteps > 0 ? (
              <>
                <div className="h-1.5 w-16 overflow-hidden rounded-full bg-ops-border/30 ring-1 ring-ops-border/20">
                  <div
                    className={`h-full rounded-full transition-all duration-700 ${isPlanMode ? 'bg-gradient-to-r from-ops-green to-emerald-300' : 'bg-gradient-to-r from-ops-green to-emerald-300'}`}
                    style={{ width: `${progress}%` }}
                  />
                </div>
                <span className="font-mono text-[10px] text-ops-muted tabular-nums">{progress}%</span>
              </>
            ) : null}
            <button
              type="button"
              className="button-mini h-7 px-2 text-[10px] uppercase tracking-[0.14em]"
              onClick={() => setShowSteps((visible) => !visible)}
              aria-expanded={showSteps}
            >
              {showSteps ? t('conversation.hide') : t('conversation.show')}
            </button>
          </div>
        </div>

        {showSteps && isPlanningEmpty ? (
          <div className="mt-3 grid gap-1.5">
            {[0, 1, 2].map((item) => (
              <div key={item} className="flex items-center gap-2 rounded-xl border border-ops-green/10 bg-ops-panel/35 px-2.5 py-2">
                <span className="h-4 w-4 rounded-full bg-ops-green/15" />
                <span className="h-2.5 flex-1 overflow-hidden rounded-full bg-ops-border/20">
                  <span className="block h-full w-1/2 animate-pulse rounded-full bg-gradient-to-r from-transparent via-ops-green/35 to-transparent" />
                </span>
              </div>
            ))}
          </div>
        ) : null}

        {showSteps && totalSteps > 0 ? (
          <ol className="mt-3 flex max-h-[min(52vh,420px)] flex-col gap-1.5 overflow-y-auto pr-1">
            {visibleSteps.map((step, index) => {
              const isRunning = step.status === 'running' || (!isFailed && !isWaitingApproval && runningStep === undefined && index === completedSteps && step.status === 'pending')
              const itemClassName = step.status === 'completed'
                ? 'border-ops-green/20 bg-ops-green/8 text-ops-green'
                : step.status === 'failed'
                  ? 'border-ops-danger/25 bg-ops-danger/10 text-ops-danger'
                : isRunning
                  ? 'border-ops-green/25 bg-ops-green/10 text-ops-green'
                  : 'border-ops-border/15 bg-ops-panel/30 text-ops-muted'
              const indexClassName = step.status === 'completed'
                ? 'bg-ops-green/15 text-ops-green ring-ops-green/20'
                : step.status === 'failed'
                  ? 'bg-ops-danger/15 text-ops-danger ring-ops-danger/25'
                : isRunning
                  ? 'bg-ops-green/15 text-ops-green ring-ops-green/25'
                  : 'bg-ops-panel/45 text-ops-muted ring-ops-border/20'

              return (
                <li key={step.id ?? `step-${index}`} className={`rounded-xl border px-2.5 py-2 text-[12px] transition-all duration-300 ${itemClassName}`} title={step.title}>
                  <div className="flex items-center gap-2.5">
                    <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-black ring-1 ${indexClassName}`}>
                      {step.status === 'completed' ? '✓' : index + 1}
                    </span>
                    <span className="min-w-0 flex-1 truncate font-semibold">{step.title}</span>
                    {isRunning ? (
                      <span className="shrink-0 rounded-full border border-ops-green/25 bg-ops-green/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.16em] text-ops-green animate-pulse">
                        {t('conversation.running')}
                      </span>
                    ) : null}
                  </div>
                </li>
              )
            })}
          </ol>
        ) : null}
      </div>
    </section>
  )
}
