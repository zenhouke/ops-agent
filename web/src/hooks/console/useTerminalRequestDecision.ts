import { useCallback, type RefObject } from 'react'
import { appendConversationEvents, streamDecideTerminalRequest } from '../../api'
import type { AgentMessage, ConversationSummary, EventItem, RuntimeSummary } from '../../types/ops'
import {
  flushDeltaBuffer,
  mergeEventsBySequence,
  upsertMessageEvent,
  upsertStreamEvent,
} from './consoleShared'
import { createDeltaBatcher } from './agentRunSupport'

type Props = {
  activeConversationId: string | null
  activeConversationIdRef: RefObject<string | null>
  latestEventsRef: RefObject<EventItem[]>
  setEvents: (updater: EventItem[] | ((previous: EventItem[]) => EventItem[])) => void
  setLoadError: (error: string | null) => void
  syncConversationRuntimes: (conversationId: string) => Promise<RuntimeSummary[]>
  upsertConversationSummary: (summary: ConversationSummary) => void
}

export function useTerminalRequestDecision({
  activeConversationId,
  activeConversationIdRef,
  latestEventsRef,
  setEvents,
  setLoadError,
  syncConversationRuntimes,
  upsertConversationSummary,
}: Props) {
  return useCallback(async (input: {
    runtimeId: string
    requestId: string
    approvalToken: string
    approved: boolean
  }) => {
    if (!activeConversationId) return
    try {
      const stream = await streamDecideTerminalRequest(input.requestId, input)
      const deltaBuffer = new Map<string, string>()
      const batcher = createDeltaBatcher({
        setEvents,
        isActive: () => activeConversationIdRef.current === activeConversationId,
      })
      const persisted: EventItem[] = []
      const messages = new Map<string, AgentMessage>()
      for await (const event of stream) {
        if (event.kind === 'message_update') {
          const message = { ...event, kind: 'message' as const } as unknown as AgentMessage
          if (activeConversationIdRef.current === activeConversationId) {
            setEvents((current) => upsertMessageEvent(current, message))
          }
          messages.set(message.id, message)
          continue
        }
        if (event.kind === 'delta' && event.messageId) {
          const text = `${deltaBuffer.get(event.messageId) || ''}${event.text}`
          deltaBuffer.set(event.messageId, text)
          if (activeConversationIdRef.current === activeConversationId) {
            batcher.push({
              messageId: event.messageId,
              text,
              stage: 'stage' in event ? event.stage : undefined,
            })
          }
          continue
        }
        if (activeConversationIdRef.current === activeConversationId) {
          setEvents((current) => upsertStreamEvent(current, event))
        }
        persisted.push(event)
      }
      batcher.flush()
      const finalEvents = mergeEventsBySequence([
        ...persisted,
        ...Array.from(messages.values()) as EventItem[],
        ...flushDeltaBuffer(deltaBuffer, latestEventsRef.current ?? []),
      ])
      if (finalEvents.length > 0) {
        const response = await appendConversationEvents(activeConversationId, finalEvents)
        upsertConversationSummary(response.conversation)
      }
      await syncConversationRuntimes(activeConversationId)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to decide terminal request.'
      setLoadError(message)
      const errorEvent: EventItem = {
        id: `terminal-decision-error-${input.requestId}-${Date.now()}`,
        kind: 'error',
        text: message,
      }
      setEvents((current) => upsertStreamEvent(current, errorEvent))
      const response = await appendConversationEvents(activeConversationId, [errorEvent])
      upsertConversationSummary(response.conversation)
      await syncConversationRuntimes(activeConversationId)
    }
  }, [
    activeConversationId,
    activeConversationIdRef,
    latestEventsRef,
    setEvents,
    setLoadError,
    syncConversationRuntimes,
    upsertConversationSummary,
  ])
}
