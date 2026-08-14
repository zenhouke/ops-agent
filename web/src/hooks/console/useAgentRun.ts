import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { appendConversationEvents, streamApproveAgent, streamRunAgent } from '../../api'
import type { AgentMessage, EventItem } from '../../types/ops'
import { flushDeltaBuffer, LOCAL_TERMINAL_ASSET_ID, mergeEventsBySequence, PENDING_ASSISTANT_MESSAGE_ID, upsertMessageEvent, upsertStreamEvent } from './consoleShared'
import {
  createDeltaBatcher,
  derivePendingApprovalState,
  getRunErrorMessage,
  isAbortError,
  type BackgroundRunState,
  type UseAgentRunProps,
} from './agentRunSupport'
import { useTerminalRequestDecision } from './useTerminalRequestDecision'
import { useAgentRunCancellation } from './useAgentRunCancellation'
import { usePlanApproval } from './usePlanApproval'


export function useAgentRun({
  activeConversationId,
  activeConversationTitle,
  activeConversationIdRef,
  events,
  setEvents,
  createConversation,
  upsertConversationSummary,
  refreshConversationList,
  syncConversationRuntimes,
  selectedAsset,
  activeTerminalTab,
  selectedModel,
  runMode,
  setLoadError,
  setContextStatus,
}: UseAgentRunProps) {
  const [pendingApprovalRuntimeId, setPendingApprovalRuntimeId] = useState<string | null>(null)
  const [pendingApprovalToken, setPendingApprovalToken] = useState<string | null>(null)
  const [backgroundRun, setBackgroundRun] = useState<BackgroundRunState | null>(null)
  const [activeRuntimeId, setActiveRuntimeId] = useState<string | null>(null)
  const activeRunAbortRef = useRef<AbortController | null>(null)
  const intentionalCancellationRef = useRef(false)
  const submittedApprovalKeyRef = useRef<string | null>(null)
  const latestEventsRef = useRef<EventItem[]>(events)

  useEffect(() => {
    latestEventsRef.current = events
  }, [events])

  const decideTerminalAccess = useTerminalRequestDecision({
    activeConversationId,
    activeConversationIdRef,
    latestEventsRef,
    setEvents,
    setLoadError,
    syncConversationRuntimes,
    upsertConversationSummary,
  })

  const activeBackgroundRun = useMemo(() => {
    if (!backgroundRun || backgroundRun.conversationId === activeConversationId) {
      return null
    }
    return backgroundRun
  }, [activeConversationId, backgroundRun])

  const clearBackgroundRunUnread = useCallback((conversationId: string) => {
    setBackgroundRun((currentRun) => {
      if (!currentRun || currentRun.conversationId !== conversationId) {
        return currentRun
      }
      return { ...currentRun, hasUnread: false }
    })
  }, [])

  useEffect(() => {
    if (activeConversationId) {
      clearBackgroundRunUnread(activeConversationId)
    }
  }, [activeConversationId, clearBackgroundRunUnread])

  useEffect(() => {
    const pendingApproval = derivePendingApprovalState(events)
    if (submittedApprovalKeyRef.current && submittedApprovalKeyRef.current === pendingApproval?.approvalKey) {
      return
    }
    submittedApprovalKeyRef.current = null
    setPendingApprovalRuntimeId(pendingApproval?.runtimeId ?? null)
    setPendingApprovalToken(pendingApproval?.approvalToken ?? null)
  }, [events])

  const runAgent = useCallback(async (runPrompt: string, selectedSkillName?: string | null) => {
    setLoadError(null)

    let conversationId = activeConversationId
    let deltaBatcher: ReturnType<typeof createDeltaBatcher> | null = null

    try {
      if (backgroundRun && backgroundRun.status !== 'completed' && backgroundRun.status !== 'failed' && backgroundRun.conversationId !== activeConversationId) {
        throw new Error(`会话「${backgroundRun.title}」正在${backgroundRun.status === 'needs_approval' ? '等待审批' : '运行'}，当前暂不支持并行执行。`)
      }

      if (!conversationId) {
        conversationId = await createConversation()
      }

      if (!conversationId) {
        throw new Error('No active conversation available for agent run.')
      }

      const userEvent: EventItem = {
        id: `user-${Date.now()}`,
        kind: 'user',
        text: runPrompt,
      }

      const pendingStatusEvent: EventItem = {
        id: PENDING_ASSISTANT_MESSAGE_ID,
        kind: 'delta',
        messageId: PENDING_ASSISTANT_MESSAGE_ID,
        stage: 'assistant',
        text: 'Initiating request and waiting for model response...',
      }

      if (activeConversationIdRef.current === conversationId) {
        setEvents((currentEvents: EventItem[]) => [...currentEvents, userEvent, pendingStatusEvent])
        setPendingApprovalRuntimeId(null)
        setPendingApprovalToken(null)
      }
      setBackgroundRun({
        conversationId,
        title: activeConversationId === conversationId ? activeConversationTitle || '当前会话' : '后台会话',
        status: 'running',
        hasUnread: false,
      })

      const abortController = new AbortController()
      activeRunAbortRef.current = abortController
      intentionalCancellationRef.current = false
      setActiveRuntimeId(null)
      const stream = await streamRunAgent(
        runPrompt,
        selectedAsset?.id === LOCAL_TERMINAL_ASSET_ID ? undefined : selectedAsset?.id,
        activeTerminalTab?.sessionId ?? null,
        selectedModel,
        conversationId,
        runMode,
        selectedSkillName,
        abortController.signal,
      )

      const deltaBuffer = new Map<string, string>()
      deltaBatcher = createDeltaBatcher({
        setEvents,
        isActive: () => activeConversationIdRef.current === conversationId,
      })
      const pendingPersistEvents: EventItem[] = []
      const latestMessageSnapshots = new Map<string, AgentMessage>()
      let requiresApproval = false

      for await (const event of stream) {
        const eventRuntimeId = (event as EventItem & { runtimeId?: string }).runtimeId
        if (eventRuntimeId) {
          setActiveRuntimeId(eventRuntimeId)
        }
        if (event.kind === 'message_update') {
          const message = { ...event, kind: 'message' as const } as unknown as AgentMessage
          const isViewingRunConversation = activeConversationIdRef.current === conversationId
          if (isViewingRunConversation) {
            setEvents((currentEvents: EventItem[]) => upsertMessageEvent(currentEvents, message))
          } else {
            setBackgroundRun((currentRun) => currentRun?.conversationId === conversationId ? { ...currentRun, hasUnread: true } : currentRun)
          }

          if (message.type === 'ask') {
            const runtimeId = (event as any).runtimeId
            if (runtimeId) {
              requiresApproval = true
              setBackgroundRun((currentRun) => currentRun?.conversationId === conversationId ? { ...currentRun, status: 'needs_approval', hasUnread: !isViewingRunConversation } : currentRun)
              if (isViewingRunConversation) {
                setPendingApprovalRuntimeId(runtimeId)
                setPendingApprovalToken(message.toolCall?.approvalToken ?? null)
              }
            }
          }

          latestMessageSnapshots.set(message.id, message)
          continue
        }

        if (event.kind === 'delta' && event.messageId) {
          const currentText = deltaBuffer.get(event.messageId) || ''
          const newText = currentText + event.text
          deltaBuffer.set(event.messageId, newText)

          const isViewingRunConversation = activeConversationIdRef.current === conversationId
          if (isViewingRunConversation) {
            deltaBatcher.push({
              messageId: event.messageId,
              text: newText,
              stage: 'stage' in event ? event.stage : undefined,
            })
          } else {
            setBackgroundRun((currentRun) => currentRun?.conversationId === conversationId ? { ...currentRun, hasUnread: true } : currentRun)
          }
          continue
        }

        if (event.kind === 'context_status') {
          if (activeConversationIdRef.current === conversationId) {
            setContextStatus((currentStatus) => ({
              contextPercent: event.contextPercent ?? currentStatus?.contextPercent ?? 0,
              contextStatus: event.contextStatus ?? currentStatus?.contextStatus ?? 'normal',
              tokenUsage: event.tokenUsage ?? currentStatus?.tokenUsage,
              knowledgeEntriesInjected: event.knowledgeEntriesInjected ?? currentStatus?.knowledgeEntriesInjected,
              knowledgeContextChars: event.knowledgeContextChars ?? currentStatus?.knowledgeContextChars,
            }))
          }
          continue
        }

        if (activeConversationIdRef.current === conversationId) {
          setEvents((currentEvents: EventItem[]) => upsertStreamEvent(currentEvents, event))
        } else {
          setBackgroundRun((currentRun) => currentRun?.conversationId === conversationId ? { ...currentRun, hasUnread: true } : currentRun)
        }

        pendingPersistEvents.push(event)

        if (event.kind === 'approval_required') {
          requiresApproval = true
          const isViewingRunConversation = activeConversationIdRef.current === conversationId
          setBackgroundRun((currentRun) => currentRun?.conversationId === conversationId ? { ...currentRun, status: 'needs_approval', hasUnread: !isViewingRunConversation } : currentRun)
          if (isViewingRunConversation) {
            setPendingApprovalRuntimeId(event.runtimeId ?? null)
            setPendingApprovalToken(event.approvalToken ?? null)
          }
        }
        if (event.kind === 'approval_decision' && activeConversationIdRef.current === conversationId) {
          setPendingApprovalRuntimeId(null)
          setPendingApprovalToken(null)
        }
      }

      deltaBatcher.flush()

      const finalMessageSnapshots = Array.from(latestMessageSnapshots.values()) as EventItem[]
      const finalEvents = flushDeltaBuffer(deltaBuffer, latestEventsRef.current)
      const allPersistEvents = mergeEventsBySequence([...pendingPersistEvents, ...finalMessageSnapshots, ...finalEvents])
      if (allPersistEvents.length > 0) {
        const response = await appendConversationEvents(conversationId, allPersistEvents)
        upsertConversationSummary(response.conversation)
      }
      await syncConversationRuntimes(conversationId)
      setBackgroundRun((currentRun) => currentRun?.conversationId === conversationId ? {
        ...currentRun,
        status: requiresApproval ? 'needs_approval' : 'completed',
        hasUnread: activeConversationIdRef.current !== conversationId,
      } : currentRun)
      if (!requiresApproval) {
        setActiveRuntimeId(null)
      }
    } catch (error) {
      deltaBatcher?.cancel()
      setActiveRuntimeId(null)
      setPendingApprovalRuntimeId(null)
      setPendingApprovalToken(null)
      if (intentionalCancellationRef.current || isAbortError(error)) {
        setBackgroundRun((currentRun) => currentRun?.conversationId === conversationId
          ? { ...currentRun, status: 'failed' }
          : currentRun)
        return
      }
      const errorMessage = getRunErrorMessage(error)
      if (!conversationId) {
        setLoadError(errorMessage)
      }

      if (conversationId) {
        setBackgroundRun((currentRun) => currentRun?.conversationId === conversationId ? { ...currentRun, status: 'failed', hasUnread: activeConversationIdRef.current !== conversationId } : currentRun)
        const errorEvent: EventItem = {
          id: `error-${Date.now()}`,
          kind: 'error',
          text: errorMessage,
        }
        if (activeConversationIdRef.current === conversationId) {
          setEvents((currentEvents) => upsertStreamEvent(currentEvents, errorEvent))
        }
        try {
          const response = await appendConversationEvents(conversationId, [errorEvent])
          upsertConversationSummary(response.conversation)
          await syncConversationRuntimes(conversationId)
        } catch {
        }
      }
    } finally {
      activeRunAbortRef.current = null
      intentionalCancellationRef.current = false
      try {
        await refreshConversationList()
      } catch {
      }
    }
  }, [
    activeConversationId,
    activeConversationTitle,
    activeConversationIdRef,
    backgroundRun,
    createConversation,
    selectedAsset,
    activeTerminalTab,
    selectedModel,
    runMode,
    setLoadError,
    setContextStatus,
    upsertConversationSummary,
    setEvents,
    refreshConversationList,
    syncConversationRuntimes,
  ])

  const submitApproval = useCallback(
    async (approved: boolean, allowPrefix?: string) => {
      if (!pendingApprovalRuntimeId || !activeConversationId) {
        return
      }

      const runId = pendingApprovalRuntimeId
      const approvalToken = pendingApprovalToken
      const conversationId = activeConversationId
      submittedApprovalKeyRef.current = derivePendingApprovalState(events)?.approvalKey ?? null
      setPendingApprovalRuntimeId(null)
      setPendingApprovalToken(null)

      if (activeConversationIdRef.current === conversationId) {
        setEvents((currentEvents: EventItem[]) => [
          ...currentEvents,
          {
            id: PENDING_ASSISTANT_MESSAGE_ID,
            kind: 'delta',
            messageId: PENDING_ASSISTANT_MESSAGE_ID,
            stage: 'assistant',
            text: approved ? 'Approval submitted, waiting for model to continue...' : 'Rejection submitted, waiting for model to continue...',
          },
        ])
      }

      try {
        const stream = await streamApproveAgent(runId, approved, approvalToken ?? undefined, allowPrefix)
        const deltaBuffer = new Map<string, string>()
        const deltaBatcher = createDeltaBatcher({
          setEvents,
          isActive: () => activeConversationIdRef.current === conversationId,
        })
        const pendingPersistEvents: EventItem[] = []
        const latestMessageSnapshots = new Map<string, AgentMessage>()
        let requiresApproval = false

        for await (const event of stream) {
          const eventRuntimeId = (event as EventItem & { runtimeId?: string }).runtimeId
          if (eventRuntimeId) {
            setActiveRuntimeId(eventRuntimeId)
          }
          if (event.kind === 'message_update') {
            const message = { ...event, kind: 'message' as const } as unknown as AgentMessage
            setEvents((currentEvents: EventItem[]) => upsertMessageEvent(currentEvents, message))

            if (message.type === 'ask' && activeConversationIdRef.current === conversationId) {
              const eventRuntimeId = (event as any).runtimeId
              if (eventRuntimeId) {
                requiresApproval = true
                setPendingApprovalRuntimeId(eventRuntimeId)
                setPendingApprovalToken(message.toolCall?.approvalToken ?? null)
              }
            }
            latestMessageSnapshots.set(message.id, message)
            continue
          }

          if (event.kind === 'delta' && event.messageId) {
            const currentText = deltaBuffer.get(event.messageId) || ''
            const newText = currentText + event.text
            deltaBuffer.set(event.messageId, newText)

            deltaBatcher.push({
              messageId: event.messageId,
              text: newText,
              stage: 'stage' in event ? event.stage : undefined,
            })
            continue
          }

          if (activeConversationIdRef.current === conversationId) {
            setEvents((currentEvents: EventItem[]) => upsertStreamEvent(currentEvents, event))
          }

          pendingPersistEvents.push(event)

          if (event.kind === 'approval_required' && activeConversationIdRef.current === conversationId) {
            requiresApproval = true
            setPendingApprovalRuntimeId(event.runtimeId ?? null)
            setPendingApprovalToken(event.approvalToken ?? null)
          }
          if (event.kind === 'approval_decision' && activeConversationIdRef.current === conversationId) {
            setPendingApprovalRuntimeId(null)
            setPendingApprovalToken(null)
          }
        }

        deltaBatcher.flush()

        const finalMessageSnapshots = Array.from(latestMessageSnapshots.values()) as EventItem[]
        const finalEvents = flushDeltaBuffer(deltaBuffer, latestEventsRef.current)
        const allPersistEvents = mergeEventsBySequence([...pendingPersistEvents, ...finalMessageSnapshots, ...finalEvents])
        if (allPersistEvents.length > 0) {
          const response = await appendConversationEvents(conversationId, allPersistEvents)
          upsertConversationSummary(response.conversation)
        }
        await syncConversationRuntimes(conversationId)
        setBackgroundRun((current) => current?.conversationId === conversationId ? {
          ...current,
          status: requiresApproval ? 'needs_approval' : 'completed',
        } : current)
        if (!requiresApproval) {
          setActiveRuntimeId(null)
        }
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Failed to submit approval.'
        setLoadError(errorMessage)

        try {
          const errorEvent: EventItem = {
            id: `error-${Date.now()}`,
            kind: 'error',
            text: errorMessage,
          }
          const response = await appendConversationEvents(conversationId, [errorEvent])
          upsertConversationSummary(response.conversation)
          await syncConversationRuntimes(conversationId)
        } catch {
        }

        if (activeConversationIdRef.current === conversationId) {
          setPendingApprovalRuntimeId(runId)
          setPendingApprovalToken(approvalToken ?? null)
        }
      } finally {
        try {
          await refreshConversationList()
        } catch {
        }
      }
    },
    [
      pendingApprovalRuntimeId,
      pendingApprovalToken,
      activeConversationId,
      activeConversationIdRef,
      setLoadError,
      upsertConversationSummary,
      setEvents,
      refreshConversationList,
      syncConversationRuntimes,
      events,
    ]
  )

  const cancelRun = useAgentRunCancellation({
    activeConversationId,
    activeRuntimeId,
    abortRef: activeRunAbortRef,
    intentionalCancellationRef,
    setActiveRuntimeId,
    setBackgroundRun,
    setEvents,
    setLoadError,
    setPendingApprovalRuntimeId,
    setPendingApprovalToken,
    syncConversationRuntimes,
  })
  const approvePlan = usePlanApproval({
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
  })

  return {
    pendingApprovalRuntimeId,
    backgroundRun,
    activeBackgroundRun,
    clearBackgroundRunUnread,
    isRunActive: Boolean(activeRuntimeId || (backgroundRun && ['running', 'needs_approval'].includes(backgroundRun.status))),
    runAgent,
    cancelRun,
    approveRun: (allowPrefix?: string) => void submitApproval(true, allowPrefix),
    approvePlan,
    rejectRun: () => void submitApproval(false),
    decideTerminalAccess,
  }
}
