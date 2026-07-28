import { useCallback, type Dispatch, type MutableRefObject, type SetStateAction } from 'react'
import { appendConversationEvents, cancelAgentRuntime } from '../../api'
import type { EventItem } from '../../types/ops'
import { upsertStreamEvent } from './consoleShared'
import type { BackgroundRunState } from './agentRunSupport'

type CancellationOptions = {
  activeConversationId: string | null
  activeRuntimeId: string | null
  abortRef: MutableRefObject<AbortController | null>
  intentionalCancellationRef: MutableRefObject<boolean>
  setActiveRuntimeId: Dispatch<SetStateAction<string | null>>
  setBackgroundRun: Dispatch<SetStateAction<BackgroundRunState | null>>
  setEvents: Dispatch<SetStateAction<EventItem[]>>
  setLoadError: (error: string | null) => void
  setPendingApprovalRuntimeId: Dispatch<SetStateAction<string | null>>
  setPendingApprovalToken: Dispatch<SetStateAction<string | null>>
  syncConversationRuntimes: (conversationId: string) => Promise<unknown>
}

export function useAgentRunCancellation({
  activeConversationId,
  activeRuntimeId,
  abortRef,
  intentionalCancellationRef,
  setActiveRuntimeId,
  setBackgroundRun,
  setEvents,
  setLoadError,
  setPendingApprovalRuntimeId,
  setPendingApprovalToken,
  syncConversationRuntimes,
}: CancellationOptions) {
  return useCallback(async () => {
    intentionalCancellationRef.current = true
    const runtimeId = activeRuntimeId
    if (!runtimeId) {
      abortRef.current?.abort()
      return
    }
    try {
      await cancelAgentRuntime(runtimeId)
      abortRef.current?.abort()
      setBackgroundRun((current) => current ? { ...current, status: 'failed' } : current)
      setPendingApprovalRuntimeId(null)
      setPendingApprovalToken(null)
      setActiveRuntimeId(null)
      if (activeConversationId) {
        const event: EventItem = {
          id: `runtime-cancelled-${runtimeId}-${Date.now()}`,
          kind: 'error',
          text: '运行已由操作员取消。',
        }
        setEvents((current) => upsertStreamEvent(current, event))
        await appendConversationEvents(activeConversationId, [event])
        await syncConversationRuntimes(activeConversationId)
      }
    } catch (error) {
      intentionalCancellationRef.current = false
      setLoadError(error instanceof Error ? error.message : '取消运行失败。')
    }
  }, [
    abortRef,
    activeConversationId,
    activeRuntimeId,
    intentionalCancellationRef,
    setActiveRuntimeId,
    setBackgroundRun,
    setEvents,
    setLoadError,
    setPendingApprovalRuntimeId,
    setPendingApprovalToken,
    syncConversationRuntimes,
  ])
}
