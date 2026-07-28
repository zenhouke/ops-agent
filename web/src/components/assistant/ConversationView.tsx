import { useEffect, useMemo, useRef, useState } from 'react'
import { EmptyState } from '../layout/EmptyState'
import type { EventItem } from '../../types/ops'
import { CommandExecutionCard } from './conversation/CommandExecutionCard'
import { PlanSummaryCard } from './conversation/PlanSummaryCard'
import { AssistantMessageContent } from './conversation/AssistantMessageContent'
import { EventCard } from './conversation/EventCard'
import { sortAssistantGroups } from './conversation/utils'
import { buildConversationGroups, buildConversationTurns, collectSettledTerminalRequestIds } from './conversation/conversationModel'

type ConversationViewProps = {
  events: EventItem[]
  hasMoreBefore?: boolean
  isLoadingOlder?: boolean
  pendingApprovalRuntimeId: string | null
  onLoadOlder?: () => Promise<void>
  onApprove?: (allowPrefix?: string) => void
  onReject?: () => void
  onApprovePlan?: (runtimeId: string) => void
  onTerminalRequestDecision?: (input: { runtimeId: string; requestId: string; approvalToken: string; approved: boolean }) => Promise<void>
}

const MAX_RENDERED_TURNS = 80

export function ConversationView({
  events,
  hasMoreBefore = false,
  isLoadingOlder = false,
  pendingApprovalRuntimeId,
  onLoadOlder,
  onApprove,
  onReject,
  onApprovePlan,
  onTerminalRequestDecision,
}: ConversationViewProps) {
  const scrollContainerRef = useRef<HTMLDivElement | null>(null)
  const shouldAutoScrollRef = useRef(true)
  const [showAllLoadedTurns, setShowAllLoadedTurns] = useState(false)

  const lastEvent = events[events.length - 1]
  const isStreamingNow = lastEvent?.kind === 'delta'
  const latestPlanEvent = useMemo(
    () => [...events].reverse().find((event) => event.kind === 'plan'),
    [events]
  )
  const settledTerminalRequestIds = useMemo(
    () => collectSettledTerminalRequestIds(events),
    [events]
  )
  const turns = useMemo(
    () => buildConversationTurns(buildConversationGroups(events)),
    [events]
  )
  const hiddenTurnCount = showAllLoadedTurns ? 0 : Math.max(0, turns.length - MAX_RENDERED_TURNS)
  const visibleTurns = hiddenTurnCount > 0 ? turns.slice(hiddenTurnCount) : turns

  useEffect(() => {
    setShowAllLoadedTurns(false)
  }, [events[0]?.id])

  useEffect(() => {
    const el = scrollContainerRef.current
    if (!el) return
    const handleScroll = () => {
      const threshold = 24
      const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight
      shouldAutoScrollRef.current = distanceToBottom <= threshold
    }
    handleScroll()
    el.addEventListener('scroll', handleScroll)
    return () => el.removeEventListener('scroll', handleScroll)
  }, [])

  useEffect(() => {
    const el = scrollContainerRef.current
    if (!el || !shouldAutoScrollRef.current) return
    el.scrollTop = el.scrollHeight
  }, [events])

  if (events.length === 0) {
    return (
      <div className="flex-1 overflow-y-auto p-4" aria-label="Assistant Conversation">
        <EmptyState title="Ready to Start" description="Enter a task and execution logs, approval requests, and results will appear here." />
      </div>
    )
  }

  return (
    <div className="relative flex flex-1 flex-col overflow-hidden" aria-label="Assistant Conversation">
      {latestPlanEvent?.mode === 'plan' ? (
        <div className="absolute right-4 top-3 z-30 w-[min(380px,calc(100%-2rem))]">
          <PlanSummaryCard event={latestPlanEvent} onApprovePlan={onApprovePlan} />
        </div>
      ) : null}
      <div ref={scrollContainerRef} className={`flex flex-1 flex-col gap-5 overflow-y-auto px-4 py-4 ${latestPlanEvent?.mode === 'plan' ? 'pt-20' : ''}`}>
        {hasMoreBefore || hiddenTurnCount > 0 ? (
          <div className="flex justify-center">
            <button
              type="button"
              className="rounded-xl border border-ops-border/30 bg-ops-panel/80 px-4 py-2 text-[11px] font-bold text-ops-muted transition hover:border-ops-cyan/40 hover:text-ops-cyan disabled:cursor-not-allowed disabled:opacity-50"
              disabled={isLoadingOlder || (!hasMoreBefore && hiddenTurnCount === 0)}
              onClick={() => {
                if (hiddenTurnCount > 0) {
                  setShowAllLoadedTurns(true)
                  return
                }
                void onLoadOlder?.()
              }}
            >
              {isLoadingOlder ? 'Loading older content...' : hiddenTurnCount > 0 ? `Show older content (${hiddenTurnCount} turns hidden)` : 'Load older content'}
            </button>
          </div>
        ) : null}
        {visibleTurns.map((turn, turnIndex) => {
          const isLastTurn = turnIndex === visibleTurns.length - 1
          const orderedAssistantGroups = sortAssistantGroups(turn.assistantGroups)

          return (
            <div key={turn.id} className="flex flex-col gap-4">
              {turn.userEvent ? (
                <EventCard
                  event={turn.userEvent}
                  pendingApprovalRuntimeId={pendingApprovalRuntimeId}
                  onApprove={onApprove}
                  onReject={onReject}
                  onTerminalRequestDecision={onTerminalRequestDecision}
                  settledTerminalRequestIds={settledTerminalRequestIds}
                />
              ) : null}

              {orderedAssistantGroups.length > 0 ? (
                <div className="flex flex-col gap-4 w-full">
                  {orderedAssistantGroups.map((entry, index) => {
                    const isLastGroupInTurn = index === orderedAssistantGroups.length - 1

                    if (entry.type === 'command') {
                      return (
                        <CommandExecutionCard
                          key={entry.key}
                          approvalEvent={entry.approvalEvent}
                          startEvent={entry.startEvent}
                          chunkEvents={entry.chunkEvents}
                          endEvent={entry.endEvent}
                          pendingApprovalRuntimeId={pendingApprovalRuntimeId}
                          onApprove={onApprove}
                          onReject={onReject}
                        />
                      )
                    }

                    if (entry.type === 'thinking') {
                      const content = entry.deltas ? entry.deltas.map(d => d.text).join('') : undefined
                      return (
                        <div key={entry.key} className="flex justify-start w-full">
                          <AssistantMessageContent
                            content={content}
                            message={entry.message}
                            isStreaming={isLastTurn && isLastGroupInTurn && (isStreamingNow || entry.message?.partial)}
                            onApprove={onApprove}
                            onReject={onReject}
                            pendingApprovalRuntimeId={pendingApprovalRuntimeId}
                          />
                        </div>
                      )
                    }

                    if (entry.type === 'event') {
                      if (entry.event.kind === 'plan') {
                        if (entry.event !== latestPlanEvent || entry.event.mode === 'plan') {
                          return null
                        }

                        return <div key={entry.event.id} className="max-w-[560px]"><PlanSummaryCard event={entry.event} onApprovePlan={onApprovePlan} /></div>
                      }

                      return (
                        <EventCard
                          key={entry.event.id}
                          event={entry.event}
                          pendingApprovalRuntimeId={pendingApprovalRuntimeId}
                          onApprove={onApprove}
                          onReject={onReject}
                          onTerminalRequestDecision={onTerminalRequestDecision}
                          settledTerminalRequestIds={settledTerminalRequestIds}
                        />
                      )
                    }

                    return null
                  })}
                </div>
              ) : null}
            </div>
          )
        })}
      </div>
    </div>
  )
}
