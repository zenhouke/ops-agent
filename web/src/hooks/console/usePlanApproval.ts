import { useCallback, type Dispatch, type SetStateAction } from 'react'
import { appendConversationEvents, streamApprovePlan } from '../../api'
import type { AgentMessage, ConversationSummary, EventItem } from '../../types/ops'
import {
  flushDeltaBuffer,
  mergeEventsBySequence,
  upsertMessageEvent,
  upsertStreamEvent,
} from './consoleShared'
import { createDeltaBatcher, type BackgroundRunState } from './agentRunSupport'

type PlanApprovalOptions = {
  activeConversationId: string | null
  activeConversationIdRef: { current: string | null }
  latestEventsRef: { current: EventItem[] }
  refreshConversationList: () => Promise<unknown>
  setActiveRuntimeId: Dispatch<SetStateAction<string | null>>
  setBackgroundRun: Dispatch<SetStateAction<BackgroundRunState | null>>
  setEvents: Dispatch<SetStateAction<EventItem[]>>
  setLoadError: (error: string | null) => void
  syncConversationRuntimes: (conversationId: string) => Promise<unknown>
  upsertConversationSummary: (conversation: ConversationSummary) => void
}

export function usePlanApproval({
  activeConversationId,
  activeConversationIdRef,
  latestEventsRef,
  refreshConversationList,
  setActiveRuntimeId,
  setBackgroundRun,
  setEvents,
  setLoadError,
  syncConversationRuntimes,
  upsertConversationSummary,
}: PlanApprovalOptions) {
  return useCallback(async (runtimeId: string) => {
    const conversationId = activeConversationId
    if (!conversationId) return
    setLoadError(null)
    setActiveRuntimeId(runtimeId)
    setBackgroundRun((current) => current?.conversationId === conversationId
      ? { ...current, status: 'running' }
      : current)
    try {
      const stream = await streamApprovePlan(runtimeId)
      const deltaBuffer = new Map<string, string>()
      const pendingPersistEvents: EventItem[] = []
      const latestMessageSnapshots = new Map<string, AgentMessage>()
      const deltaBatcher = createDeltaBatcher({
        setEvents,
        isActive: () => activeConversationIdRef.current === conversationId,
      })
      let requiresApproval = false

      for await (const event of stream) {
        if (event.kind === 'message_update') {
          const message = { ...event, kind: 'message' as const } as unknown as AgentMessage
          setEvents((current) => upsertMessageEvent(current, message))
          latestMessageSnapshots.set(message.id, message)
          if (message.type === 'ask') requiresApproval = true
          continue
        }
        if (event.kind === 'delta' && event.messageId) {
          const text = (deltaBuffer.get(event.messageId) || '') + event.text
          deltaBuffer.set(event.messageId, text)
          deltaBatcher.push({
            messageId: event.messageId,
            text,
            stage: 'stage' in event ? event.stage : undefined,
          })
          continue
        }
        if (event.kind === 'approval_required') requiresApproval = true
        setEvents((current) => upsertStreamEvent(current, event))
        pendingPersistEvents.push(event)
      }

      deltaBatcher.flush()
      const persistEvents = mergeEventsBySequence([
        ...pendingPersistEvents,
        ...Array.from(latestMessageSnapshots.values()) as EventItem[],
        ...flushDeltaBuffer(deltaBuffer, latestEventsRef.current),
      ])
      if (persistEvents.length > 0) {
        const response = await appendConversationEvents(conversationId, persistEvents)
        upsertConversationSummary(response.conversation)
      }
      await syncConversationRuntimes(conversationId)
      setBackgroundRun((current) => current?.conversationId === conversationId
        ? { ...current, status: requiresApproval ? 'needs_approval' : 'completed' }
        : current)
      if (!requiresApproval) setActiveRuntimeId(null)
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : '批准计划失败。')
      setBackgroundRun((current) => current?.conversationId === conversationId
        ? { ...current, status: 'failed' }
        : current)
    } finally {
      await refreshConversationList().catch(() => undefined)
    }
  }, [
    activeConversationId,
    activeConversationIdRef,
    latestEventsRef,
    refreshConversationList,
    setActiveRuntimeId,
    setBackgroundRun,
    setEvents,
    setLoadError,
    syncConversationRuntimes,
    upsertConversationSummary,
  ])
}
