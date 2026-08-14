import { useEffect, useMemo, useRef, useState } from 'react'
import { EmptyState } from '../layout/EmptyState'
import type { EventItem } from '../../types/ops'
import { CommandExecutionCard } from './conversation/CommandExecutionCard'
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
  onTerminalRequestDecision,
}: ConversationViewProps) {
  const scrollContainerRef = useRef<HTMLDivElement | null>(null)
  const shouldAutoScrollRef = useRef(true)
  const [showAllLoadedTurns, setShowAllLoadedTurns] = useState(false)

  const lastEvent = events[events.length - 1]
  const isStreamingNow = lastEvent?.kind === 'delta'
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
      <div className="flex-1 overflow-y-auto p-3" aria-label="任务执行记录">
        <EmptyState title="准备就绪" description="输入任务后，执行记录、审批请求和最终结果会显示在这里。" />
      </div>
    )
  }

  return (
    <div className="relative flex flex-1 flex-col overflow-hidden" aria-label="任务执行记录">
      <div ref={scrollContainerRef} className="mx-auto flex w-full max-w-[980px] flex-1 flex-col gap-2 overflow-y-auto px-5 py-4">
        {hasMoreBefore || hiddenTurnCount > 0 ? (
          <div className="flex justify-center">
            <button
              type="button"
              className="rounded-[4px] border border-ops-border/30 bg-ops-panel/80 px-3 py-1.5 text-[10px] font-semibold text-ops-muted transition hover:border-ops-cyan/40 hover:text-ops-cyan disabled:cursor-not-allowed disabled:opacity-50"
              disabled={isLoadingOlder || (!hasMoreBefore && hiddenTurnCount === 0)}
              onClick={() => {
                if (hiddenTurnCount > 0) {
                  setShowAllLoadedTurns(true)
                  return
                }
                void onLoadOlder?.()
              }}
            >
              {isLoadingOlder ? '正在加载更早内容…' : hiddenTurnCount > 0 ? `显示更早内容（已隐藏 ${hiddenTurnCount} 轮）` : '加载更早内容'}
            </button>
          </div>
        ) : null}
        {visibleTurns.map((turn, turnIndex) => {
          const isLastTurn = turnIndex === visibleTurns.length - 1
          const orderedAssistantGroups = sortAssistantGroups(turn.assistantGroups)

          return (
            <section key={turn.id} className="relative flex flex-col gap-2 border-l border-ops-border/25 pb-4 pl-5 before:absolute before:-left-[4px] before:top-2 before:h-[7px] before:w-[7px] before:rounded-full before:border before:border-ops-cyan/40 before:bg-ops-bg">
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
                <div className="flex w-full flex-col gap-3">
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
            </section>
          )
        })}
      </div>
    </div>
  )
}
