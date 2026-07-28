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
  const isWaitingApproval = isPlanMode && event.lockedPlan === false && !event.interrupted
  const [showSteps, setShowSteps] = useState(true)
  const visibleSteps = event.steps
  const totalSteps = visibleSteps.length
  const completedSteps = visibleSteps.filter((step) => step.status === 'completed').length
  const runningStep = visibleSteps.find((step) => step.status === 'running')
  const progress = totalSteps > 0 ? Math.round((completedSteps / totalSteps) * 100) : 0
  const title = event.title?.trim()
  const displayTitle = title || (isPlanMode ? t('conversation.executionPlan') : t('conversation.taskPlan'))
  const isPlanningEmpty = event.loading && totalSteps === 0
  const statusLabel = event.loading
    ? t('conversation.planning')
    : event.interrupted
      ? '运行已中断'
    : isWaitingApproval
      ? '等待操作员批准'
      : isPlanMode
      ? t('conversation.autoExecuting')
      : t('assistant.plan')

  return (
    <section className={`relative overflow-hidden border border-ops-cyan/18 bg-ops-deep/88 shadow-[0_10px_28px_rgb(var(--ops-bg)/0.18),inset_0_1px_0_rgb(var(--ops-text)/0.04)] backdrop-blur-xl transition-all duration-200 ${showSteps ? 'rounded-2xl' : 'rounded-full'}`}>
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-ops-cyan/50 to-transparent" />
      <div className={showSteps ? 'p-2.5' : 'px-3 py-2'}>
        <div className={`flex items-center justify-between gap-2 ${showSteps ? 'flex-wrap' : ''}`}>
          <div className="min-w-0 flex flex-1 items-center gap-2">
            <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${event.loading ? 'animate-pulse bg-ops-cyan shadow-[0_0_16px_rgb(var(--ops-cyan)/0.55)]' : isPlanMode ? 'bg-ops-cyan' : 'bg-ops-green'}`} />
            <div className="min-w-0">
              <div className="flex min-w-0 items-center gap-2">
                <h3 className="truncate text-[11px] font-black uppercase tracking-[0.2em] text-ops-text/95">
                  {showSteps ? displayTitle : t('conversation.taskPlan')}
                </h3>
                {showSteps && event.updated ? (
                  <span className="rounded-full border border-ops-warning/30 bg-ops-warning/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-[0.16em] text-ops-warning">
                    {t('conversation.updated')}
                  </span>
                ) : null}
                {showSteps && isPlanMode ? (
                  <span className="inline-flex items-center gap-1 rounded-full border border-ops-cyan/30 bg-ops-cyan/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-[0.14em] text-ops-cyan">
                    <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M5 3v18l15-9-15-9z" />
                    </svg>
                    {event.interrupted ? '已中断' : isWaitingApproval ? '手动批准' : t('conversation.autoExecute')}
                  </span>
                ) : null}
              </div>
              <div className={`flex items-center gap-2 text-[10px] text-ops-muted ${showSteps ? 'mt-1' : ''}`}>
                <span className={event.loading || isPlanMode ? 'text-ops-cyan' : undefined}>{statusLabel}</span>
                {totalSteps > 0 ? <span className="tabular-nums">{completedSteps}/{totalSteps}</span> : null}
                {showSteps && typeof event.version === 'number' && event.version > 0 ? (
                  <span className="rounded-md bg-ops-panel/55 px-1.5 py-0.5 font-mono text-[9px] text-ops-muted/90">v{event.version}</span>
                ) : null}
              </div>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {showSteps && isWaitingApproval && event.runtimeId ? (
              <button
                type="button"
                className="button-mini h-7 border-ops-cyan/35 bg-ops-cyan/10 px-2.5 text-[10px] font-black text-ops-cyan transition-all duration-200 hover:bg-ops-cyan/20 active:scale-95"
                onClick={() => onApprovePlan?.(event.runtimeId!)}
              >
                批准并执行
              </button>
            ) : null}
            {showSteps && totalSteps > 0 ? (
              <>
                <div className="h-1.5 w-16 overflow-hidden rounded-full bg-ops-border/30 ring-1 ring-ops-border/20">
                  <div
                    className={`h-full rounded-full transition-all duration-700 ${isPlanMode ? 'bg-gradient-to-r from-ops-cyan to-emerald-300' : 'bg-gradient-to-r from-ops-green to-emerald-300'}`}
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
              <div key={item} className="flex items-center gap-2 rounded-xl border border-ops-cyan/10 bg-ops-panel/35 px-2.5 py-2">
                <span className="h-4 w-4 rounded-full bg-ops-cyan/15" />
                <span className="h-2.5 flex-1 overflow-hidden rounded-full bg-ops-border/20">
                  <span className="block h-full w-1/2 animate-pulse rounded-full bg-gradient-to-r from-transparent via-ops-cyan/35 to-transparent" />
                </span>
              </div>
            ))}
          </div>
        ) : null}

        {showSteps && totalSteps > 0 ? (
          <ol className="mt-3 flex max-h-[min(52vh,420px)] flex-col gap-1.5 overflow-y-auto pr-1">
            {visibleSteps.map((step, index) => {
              const isRunning = step.status === 'running'
                || (!event.interrupted && !isWaitingApproval && runningStep === undefined && index === completedSteps && step.status === 'pending')
              const itemClassName = step.status === 'completed'
                ? 'border-ops-green/25 bg-ops-green/8 text-ops-green'
                : isRunning
                  ? 'border-ops-cyan/35 bg-ops-cyan/10 text-ops-cyan shadow-[0_0_0_1px_rgb(var(--ops-cyan)/0.16),0_10px_24px_rgb(var(--ops-cyan)/0.08)]'
                  : 'border-ops-border/20 bg-ops-panel/35 text-ops-muted'
              const indexClassName = step.status === 'completed'
                ? 'bg-ops-green/15 text-ops-green ring-ops-green/25'
                : isRunning
                  ? 'bg-ops-cyan/15 text-ops-cyan ring-ops-cyan/35'
                  : 'bg-ops-panel/45 text-ops-muted ring-ops-border/25'

              return (
                <li key={step.id ?? `step-${index}`} className={`rounded-xl border px-2.5 py-2 text-[12px] transition-all duration-300 ${itemClassName}`} title={step.title}>
                  <div className="flex items-center gap-2.5">
                    <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-black ring-1 ${indexClassName}`}>
                      {step.status === 'completed' ? '✓' : index + 1}
                    </span>
                    <span className="min-w-0 flex-1 truncate font-semibold">{step.title}</span>
                    {isRunning ? (
                      <span className="shrink-0 rounded-full border border-ops-cyan/25 bg-ops-cyan/10 px-2 py-0.5 text-[9px] font-bold uppercase tracking-[0.16em] text-ops-cyan animate-pulse">
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
