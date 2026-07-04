import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from 'react'
import { appendConversationEvents, streamApproveAgent, streamApprovePlan, streamDecideTerminalRequest, streamRunAgent } from '../../api'
import type { RunMode } from '../../types/api'
import type { AgentMessage, Asset, ConversationContextStatus, ConversationSummary, EventItem, RuntimeSummary } from '../../types/ops'
import { getApprovalKeys, isApprovalSettlingEvent } from '../../utils/approvalState'
import { finalizeOpenPartialMessages, flushDeltaBuffer, isTerminalStreamEvent, LOCAL_TERMINAL_ASSET_ID, mergeDeltaEvent, mergeEventsBySequence, PENDING_ASSISTANT_MESSAGE_ID, upsertMessageEvent, upsertStreamEvent } from './consoleShared'

interface UseAgentRunProps {
  // Conversation dependencies
  activeConversationId: string | null
  activeConversationTitle: string
  activeConversationIdRef: RefObject<string | null>
  events: EventItem[]
  setEvents: (updater: EventItem[] | ((prev: EventItem[]) => EventItem[])) => void
  createConversation: () => Promise<string>
  upsertConversationSummary: (summary: ConversationSummary) => void
  refreshConversationList: () => Promise<any>
  syncConversationRuntimes: (conversationId: string) => Promise<RuntimeSummary[]>
  runtimeSummaries: RuntimeSummary[]

  // Terminal dependencies
  selectedAsset: Asset
  activeTerminalTab: { sessionId: string | null } | null

  // Base state dependencies
  selectedModel: string
  runMode: RunMode
  setLoadError: (error: string | null) => void
  setContextStatus: (status: ConversationContextStatus | null | ((currentStatus: ConversationContextStatus | null) => ConversationContextStatus)) => void
}

type BackgroundRunStatus = 'running' | 'needs_approval' | 'completed' | 'failed'

type BackgroundRunState = {
  conversationId: string
  title: string
  status: BackgroundRunStatus
  hasUnread: boolean
}

type PendingApprovalState = {
  runtimeId: string
  approvalToken: string | null
  approvalKey: string
  terminalId: string | null
}

type DeltaBatchItem = {
  messageId: string
  text: string
  stage?: string
}

function markWaitingPlanFailed(events: EventItem[], runtimeId: string, errorMessage: string): EventItem[] {
  let updated = false
  const nextEvents = events.map((event) => {
    if (
      event.kind !== 'plan'
      || event.runtimeId !== runtimeId
      || event.status !== 'waiting_plan_approval'
    ) {
      return event
    }
    updated = true
    return {
      ...event,
      id: `${event.id}-failed-${Date.now()}`,
      status: 'failed',
      lockedPlan: true,
      updated: true,
      error: errorMessage,
      steps: event.steps.map((step) => step.status === 'completed' ? step : { ...step, status: 'failed' as const }),
    }
  })
  return updated ? nextEvents : events
}

function backgroundStatusFromRuntime(status: string | undefined, fallback: BackgroundRunStatus): BackgroundRunStatus {
  if (status === 'approving' || status === 'waiting_terminal_approval' || status === 'waiting_plan_approval') {
    return 'needs_approval'
  }
  if (status === 'failed') {
    return 'failed'
  }
  if (status === 'completed') {
    return 'completed'
  }
  return fallback
}

function backgroundStatusForRuntime(
  runtimes: RuntimeSummary[],
  runtimeId: string | null,
  fallback: BackgroundRunStatus
): BackgroundRunStatus {
  if (!runtimeId) {
    return fallback
  }
  return backgroundStatusFromRuntime(
    runtimes.find((runtime) => runtime.runtimeId === runtimeId)?.status,
    fallback
  )
}

function eventRuntimeId(event: EventItem): string | null {
  const runtimeId = (event as any).runtimeId
  return typeof runtimeId === 'string' && runtimeId ? runtimeId : null
}

const DELTA_FLUSH_INTERVAL_MS = 60

function createDeltaBatcher({
  setEvents,
  isActive,
}: {
  setEvents: UseAgentRunProps['setEvents']
  isActive: () => boolean
}) {
  const pending = new Map<string, DeltaBatchItem>()
  let timer: ReturnType<typeof window.setTimeout> | null = null

  const flush = () => {
    if (timer !== null) {
      window.clearTimeout(timer)
      timer = null
    }
    if (pending.size === 0 || !isActive()) {
      pending.clear()
      return
    }
    const items = Array.from(pending.values())
    pending.clear()
    setEvents((currentEvents: EventItem[]) =>
      items.reduce(
        (nextEvents, item) => mergeDeltaEvent(nextEvents, item.messageId, item.text, item.stage),
        currentEvents
      )
    )
  }

  const scheduleFlush = () => {
    if (timer !== null) {
      return
    }
    timer = window.setTimeout(flush, DELTA_FLUSH_INTERVAL_MS)
  }

  return {
    push(item: DeltaBatchItem) {
      pending.set(item.messageId, item)
      scheduleFlush()
    },
    flush,
  }
}

function getApprovalKey(event: EventItem) {
  return getApprovalKeys(event)[0] ?? null
}

function derivePendingApprovalState(events: EventItem[]): PendingApprovalState | null {
  const settledApprovalKeys = new Set<string>()

  for (let index = events.length - 1; index >= 0; index--) {
    const event = events[index]
    const approvalKey = getApprovalKey(event)

    if (approvalKey && isApprovalSettlingEvent(event)) {
      getApprovalKeys(event).forEach((key) => settledApprovalKeys.add(key))
      continue
    }

    if (approvalKey && settledApprovalKeys.has(approvalKey)) {
      continue
    }

    if (approvalKey && event.kind === 'approval_required' && event.status !== 'approved' && event.status !== 'rejected' && event.runtimeId) {
      const terminalId = typeof event.terminalId === 'string' ? event.terminalId : null
      return { runtimeId: event.runtimeId, approvalToken: event.approvalToken ?? null, approvalKey, terminalId }
    }

    if (approvalKey && 'type' in event && event.type === 'ask') {
      const runtimeId = (event as any).runtimeId
      if (runtimeId) {
        const terminalId = typeof event.toolCall?.args?.terminal_id === 'string' ? event.toolCall.args.terminal_id : null
        return { runtimeId, approvalToken: event.toolCall?.approvalToken ?? null, approvalKey, terminalId }
      }
    }
  }

  return null
}

function isLiveCommandApprovalRuntime(runtime: RuntimeSummary): boolean {
  return runtime.status === 'approving' && Boolean(runtime.pendingApprovalStepId)
}

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
  runtimeSummaries,
  selectedAsset,
  activeTerminalTab,
  selectedModel,
  runMode,
  setLoadError,
  setContextStatus,
}: UseAgentRunProps) {
  const [pendingApprovalRuntimeId, setPendingApprovalRuntimeId] = useState<string | null>(null)
  const [pendingApprovalToken, setPendingApprovalToken] = useState<string | null>(null)
  const [pendingApprovalTerminalId, setPendingApprovalTerminalId] = useState<string | null>(null)
  const [backgroundRun, setBackgroundRun] = useState<BackgroundRunState | null>(null)
  const submittedApprovalKeyRef = useRef<string | null>(null)
  const latestEventsRef = useRef<EventItem[]>(events)

  useEffect(() => {
    latestEventsRef.current = events
  }, [events])

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
    const runtimeSummary = pendingApproval
      ? runtimeSummaries.find((runtime) => runtime.runtimeId === pendingApproval.runtimeId)
      : null
    const livePendingApproval = pendingApproval && (
      (runtimeSummary && isLiveCommandApprovalRuntime(runtimeSummary))
      || (!runtimeSummary && pendingApprovalRuntimeId === pendingApproval.runtimeId)
    )
      ? pendingApproval
      : null

    if (submittedApprovalKeyRef.current && submittedApprovalKeyRef.current === livePendingApproval?.approvalKey) {
      return
    }
    submittedApprovalKeyRef.current = null
    setPendingApprovalRuntimeId(livePendingApproval?.runtimeId ?? null)
    setPendingApprovalToken(livePendingApproval?.approvalToken ?? null)
    setPendingApprovalTerminalId(livePendingApproval?.terminalId ?? null)
  }, [events, pendingApprovalRuntimeId, runtimeSummaries])

  const runAgent = useCallback(async (runPrompt: string, selectedSkillName?: string | null) => {
    setLoadError(null)

    let conversationId = activeConversationId

    try {
      if (backgroundRun && backgroundRun.status !== 'completed' && backgroundRun.status !== 'failed' && backgroundRun.conversationId !== activeConversationId) {
        throw new Error('Conversation \"' + backgroundRun.title + '\" is ' + (backgroundRun.status === 'needs_approval' ? 'waiting for approval' : 'running') + '; concurrent runs are not supported yet.')
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
        setPendingApprovalTerminalId(null)
      }
      setBackgroundRun({
        conversationId,
        title: activeConversationId === conversationId ? activeConversationTitle || '当前会话' : '后台会话',
        status: 'running',
        hasUnread: false,
      })

      const stream = await streamRunAgent(
        runPrompt,
        selectedAsset?.id === LOCAL_TERMINAL_ASSET_ID ? undefined : selectedAsset?.id,
        activeTerminalTab?.sessionId ?? null,
        selectedModel,
        conversationId,
        runMode,
        selectedSkillName,
      )

      const deltaBuffer = new Map<string, string>()
      const deltaBatcher = createDeltaBatcher({
        setEvents,
        isActive: () => activeConversationIdRef.current === conversationId,
      })
      const pendingPersistEvents: EventItem[] = []
      const latestMessageSnapshots = new Map<string, AgentMessage>()
      let streamTerminalStatus: BackgroundRunStatus | null = null
      let streamRuntimeId: string | null = null

      for await (const event of stream) {
        streamRuntimeId = eventRuntimeId(event) ?? streamRuntimeId

        if (event.kind === 'message_update') {
          // In the new protocol, the message fields are spread into the event
          const message = { ...event, kind: 'message' as const } as unknown as AgentMessage
          const isViewingRunConversation = activeConversationIdRef.current === conversationId
          if (isViewingRunConversation) {
            setEvents((currentEvents: EventItem[]) => upsertMessageEvent(currentEvents, message))
          } else {
            setBackgroundRun((currentRun) => currentRun?.conversationId === conversationId ? { ...currentRun, hasUnread: true } : currentRun)
          }

          if (message.type === 'ask') {
            streamTerminalStatus = 'needs_approval'
            const runtimeId = (event as any).runtimeId
            if (runtimeId) {
              setBackgroundRun((currentRun) => currentRun?.conversationId === conversationId ? { ...currentRun, status: 'needs_approval', hasUnread: !isViewingRunConversation } : currentRun)
              if (isViewingRunConversation) {
                setPendingApprovalRuntimeId(runtimeId)
                setPendingApprovalToken(message.toolCall?.approvalToken ?? null)
                setPendingApprovalTerminalId(typeof message.toolCall?.args?.terminal_id === 'string' ? message.toolCall.args.terminal_id : null)
              }
            }
          }

          // Track latest snapshot per message ID - only the final version will be persisted
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

        // Immediately update UI with transient event, don't block SSE stream
        if (activeConversationIdRef.current === conversationId) {
          setEvents((currentEvents: EventItem[]) => upsertStreamEvent(currentEvents, event))
        } else {
          setBackgroundRun((currentRun) => currentRun?.conversationId === conversationId ? { ...currentRun, hasUnread: true } : currentRun)
        }

        // Collect non-delta events, batch persist after stream ends
        pendingPersistEvents.push(event)

        if (isTerminalStreamEvent(event) && activeConversationIdRef.current === conversationId) {
          setEvents((currentEvents: EventItem[]) => finalizeOpenPartialMessages(currentEvents))
        }
        if (event.kind === 'approval_required') {
          streamTerminalStatus = 'needs_approval'
          const isViewingRunConversation = activeConversationIdRef.current === conversationId
          setBackgroundRun((currentRun) => currentRun?.conversationId === conversationId ? { ...currentRun, status: 'needs_approval', hasUnread: !isViewingRunConversation } : currentRun)
          if (isViewingRunConversation) {
            setPendingApprovalRuntimeId(event.runtimeId ?? null)
            setPendingApprovalToken(event.approvalToken ?? null)
          }
        }
        if (event.kind === 'failed' || event.kind === 'error') {
          streamTerminalStatus = 'failed'
        }
        if (event.kind === 'completed' || event.kind === 'final') {
          streamTerminalStatus = 'completed'
        }
        if (event.kind === 'approval_decision' && activeConversationIdRef.current === conversationId) {
          setPendingApprovalRuntimeId(null)
          setPendingApprovalToken(null)
        }
      }

      deltaBatcher.flush()

      // Batch persist: only the latest snapshot per message, plus non-delta events
      const finalMessageSnapshots = finalizeOpenPartialMessages(Array.from(latestMessageSnapshots.values()) as EventItem[])
      const finalEvents = flushDeltaBuffer(deltaBuffer, latestEventsRef.current)
      const allPersistEvents = mergeEventsBySequence([...pendingPersistEvents, ...finalMessageSnapshots, ...finalEvents])
      if (allPersistEvents.length > 0) {
        const response = await appendConversationEvents(conversationId, allPersistEvents)
        upsertConversationSummary(response.conversation)
      }
      const runtimes = await syncConversationRuntimes(conversationId)
      const finalStatus = backgroundStatusForRuntime(runtimes, streamRuntimeId, streamTerminalStatus ?? 'completed')
      setBackgroundRun((currentRun) => currentRun?.conversationId === conversationId ? { ...currentRun, status: finalStatus, hasUnread: activeConversationIdRef.current !== conversationId } : currentRun)
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to run agent.'
      if (!conversationId || activeConversationIdRef.current === conversationId) {
        setLoadError(errorMessage)
      }

      if (conversationId) {
        setBackgroundRun((currentRun) => currentRun?.conversationId === conversationId ? { ...currentRun, status: 'failed', hasUnread: activeConversationIdRef.current !== conversationId } : currentRun)
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
          // Fall back to loadError if persisting the error event also fails.
        }
      }
    } finally {
      try {
        await refreshConversationList()
      } catch {
        // Keep the main error surfaced via loadError without throwing from cleanup.
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
    async (approved: boolean, options: { allowPrefix?: string; terminalId?: string | null } = {}) => {
      if (!pendingApprovalRuntimeId || !activeConversationId) {
        return
      }

      const runId = pendingApprovalRuntimeId
      const approvalToken = pendingApprovalToken
      const terminalId = options.terminalId ?? pendingApprovalTerminalId
      const conversationId = activeConversationId
      submittedApprovalKeyRef.current = derivePendingApprovalState(events)?.approvalKey ?? null
      setPendingApprovalRuntimeId(null)
      setPendingApprovalToken(null)
      setPendingApprovalTerminalId(null)

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
        const stream = await streamApproveAgent(runId, approved, approvalToken ?? undefined, options.allowPrefix, terminalId)
        const deltaBuffer = new Map<string, string>()
        const deltaBatcher = createDeltaBatcher({
          setEvents,
          isActive: () => activeConversationIdRef.current === conversationId,
        })
        const pendingPersistEvents: EventItem[] = []
        const latestMessageSnapshots = new Map<string, AgentMessage>()
        let streamTerminalStatus: BackgroundRunStatus | null = null
        let streamRuntimeId: string | null = runId

        for await (const event of stream) {
          streamRuntimeId = eventRuntimeId(event) ?? streamRuntimeId

          if (event.kind === 'message_update') {
            const message = { ...event, kind: 'message' as const } as unknown as AgentMessage
            setEvents((currentEvents: EventItem[]) => upsertMessageEvent(currentEvents, message))

            if (message.type === 'ask' && activeConversationIdRef.current === conversationId) {
              const eventRuntimeId = (event as any).runtimeId
              if (eventRuntimeId) {
                streamTerminalStatus = 'needs_approval'
                setPendingApprovalRuntimeId(eventRuntimeId)
                setPendingApprovalToken(message.toolCall?.approvalToken ?? null)
                setPendingApprovalTerminalId(typeof message.toolCall?.args?.terminal_id === 'string' ? message.toolCall.args.terminal_id : null)
                setBackgroundRun((currentRun) => currentRun?.conversationId === conversationId ? { ...currentRun, status: 'needs_approval', hasUnread: activeConversationIdRef.current !== conversationId } : currentRun)
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

          // Immediately update UI with transient event, don't block SSE stream
          if (activeConversationIdRef.current === conversationId) {
            setEvents((currentEvents: EventItem[]) => upsertStreamEvent(currentEvents, event))
          }

          // Collect non-delta events, batch persist after stream ends
          pendingPersistEvents.push(event)

          if (isTerminalStreamEvent(event) && activeConversationIdRef.current === conversationId) {
            setEvents((currentEvents: EventItem[]) => finalizeOpenPartialMessages(currentEvents))
          }
          if (event.kind === 'approval_required' && activeConversationIdRef.current === conversationId) {
            streamTerminalStatus = 'needs_approval'
            setPendingApprovalRuntimeId(event.runtimeId ?? null)
            setPendingApprovalToken(event.approvalToken ?? null)
            setPendingApprovalTerminalId(typeof event.terminalId === 'string' ? event.terminalId : null)
            setBackgroundRun((currentRun) => currentRun?.conversationId === conversationId ? { ...currentRun, status: 'needs_approval', hasUnread: activeConversationIdRef.current !== conversationId } : currentRun)
          }
          if (event.kind === 'approval_decision' && activeConversationIdRef.current === conversationId) {
            setPendingApprovalRuntimeId(null)
            setPendingApprovalToken(null)
            setPendingApprovalTerminalId(null)
            streamTerminalStatus = event.approved === false ? 'failed' : 'running'
            setBackgroundRun((currentRun) => currentRun?.conversationId === conversationId ? { ...currentRun, status: streamTerminalStatus ?? 'running', hasUnread: activeConversationIdRef.current !== conversationId } : currentRun)
          }
          if (event.kind === 'command_start') {
            streamTerminalStatus = 'running'
            setBackgroundRun((currentRun) => currentRun?.conversationId === conversationId ? { ...currentRun, status: 'running', hasUnread: activeConversationIdRef.current !== conversationId } : currentRun)
          }
          if (event.kind === 'command_end' && event.exitCode !== null && event.exitCode !== 0) {
            streamTerminalStatus = 'failed'
          }
          if (event.kind === 'failed' || event.kind === 'error') {
            streamTerminalStatus = 'failed'
          }
          if (event.kind === 'completed' || event.kind === 'final') {
            streamTerminalStatus = 'completed'
          }
        }

        deltaBatcher.flush()

        // Batch persist all non-delta events + message snapshots + delta buffer after stream ends
        const finalMessageSnapshots = finalizeOpenPartialMessages(Array.from(latestMessageSnapshots.values()) as EventItem[])
        const finalEvents = flushDeltaBuffer(deltaBuffer, latestEventsRef.current)
        const allPersistEvents = mergeEventsBySequence([...pendingPersistEvents, ...finalMessageSnapshots, ...finalEvents])
        if (allPersistEvents.length > 0) {
          const response = await appendConversationEvents(conversationId, allPersistEvents)
          upsertConversationSummary(response.conversation)
        }
        const runtimes = await syncConversationRuntimes(conversationId)
        const finalStatus = backgroundStatusForRuntime(runtimes, streamRuntimeId, streamTerminalStatus ?? 'completed')
        setBackgroundRun((currentRun) => currentRun?.conversationId === conversationId ? { ...currentRun, status: finalStatus, hasUnread: activeConversationIdRef.current !== conversationId } : currentRun)
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
          // Fall back to loadError if persisting the error event also fails.
        }

        if (activeConversationIdRef.current === conversationId) {
          setPendingApprovalRuntimeId(runId)
          setPendingApprovalToken(approvalToken ?? null)
          setPendingApprovalTerminalId(terminalId ?? null)
        }
      } finally {
        try {
          await refreshConversationList()
        } catch {
          // Keep the main error surfaced via loadError without throwing from cleanup.
        }
      }
    },
    [
      pendingApprovalRuntimeId,
      pendingApprovalToken,
      pendingApprovalTerminalId,
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

  const decideTerminalAccess = useCallback(async (input: {
    runtimeId: string
    requestId: string
    approvalToken: string
    approved: boolean
  }) => {
    if (!activeConversationId) {
      return
    }

    const persistEvent = async (event: EventItem) => {
      if (activeConversationIdRef.current === activeConversationId) {
        setEvents((currentEvents: EventItem[]) => upsertStreamEvent(currentEvents, event))
      }
      const response = await appendConversationEvents(activeConversationId, [event])
      upsertConversationSummary(response.conversation)
    }

    try {
      const stream = await streamDecideTerminalRequest(input.requestId, {
        runtimeId: input.runtimeId,
        approvalToken: input.approvalToken,
        approved: input.approved,
      })
      const deltaBuffer = new Map<string, string>()
      const deltaBatcher = createDeltaBatcher({
        setEvents,
        isActive: () => activeConversationIdRef.current === activeConversationId,
      })
      const pendingPersistEvents: EventItem[] = []
      const latestMessageSnapshots = new Map<string, AgentMessage>()

      for await (const event of stream) {
        if (event.kind === 'message_update') {
          const message = { ...event, kind: 'message' as const } as unknown as AgentMessage
          if (activeConversationIdRef.current === activeConversationId) {
            setEvents((currentEvents: EventItem[]) => upsertMessageEvent(currentEvents, message))
          }
          latestMessageSnapshots.set(message.id, message)
          continue
        }

        if (event.kind === 'delta' && event.messageId) {
          const currentText = deltaBuffer.get(event.messageId) || ''
          const newText = currentText + event.text
          deltaBuffer.set(event.messageId, newText)
          if (activeConversationIdRef.current === activeConversationId) {
            deltaBatcher.push({
              messageId: event.messageId,
              text: newText,
              stage: 'stage' in event ? event.stage : undefined,
            })
          }
          continue
        }

        if (activeConversationIdRef.current === activeConversationId) {
          setEvents((currentEvents: EventItem[]) => upsertStreamEvent(currentEvents, event))
        }
        pendingPersistEvents.push(event)
        if (isTerminalStreamEvent(event) && activeConversationIdRef.current === activeConversationId) {
          setEvents((currentEvents: EventItem[]) => finalizeOpenPartialMessages(currentEvents))
        }
      }

      deltaBatcher.flush()

      const finalMessageSnapshots = finalizeOpenPartialMessages(Array.from(latestMessageSnapshots.values()) as EventItem[])
      const finalEvents = flushDeltaBuffer(deltaBuffer, latestEventsRef.current)
      const allPersistEvents = mergeEventsBySequence([...pendingPersistEvents, ...finalMessageSnapshots, ...finalEvents])
      if (allPersistEvents.length > 0) {
        const response = await appendConversationEvents(activeConversationId, allPersistEvents)
        upsertConversationSummary(response.conversation)
      }
      await syncConversationRuntimes(activeConversationId)
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to decide terminal request.'
      setLoadError(errorMessage)
      await persistEvent({
        id: `terminal-decision-error-${input.requestId}-${Date.now()}`,
        kind: 'error',
        text: errorMessage,
      })
      await syncConversationRuntimes(activeConversationId)
    }
  }, [activeConversationId, activeConversationIdRef, setEvents, setLoadError, syncConversationRuntimes, upsertConversationSummary])

  const approvePlanRun = useCallback(async (runtimeId: string) => {
    const conversationId = activeConversationId
    if (!conversationId) {
      return
    }

    try {
      const stream = await streamApprovePlan(runtimeId)
      const deltaBuffer = new Map<string, string>()
      const deltaBatcher = createDeltaBatcher({
        setEvents,
        isActive: () => activeConversationIdRef.current === conversationId,
      })
      const pendingPersistEvents: EventItem[] = []
      const latestMessageSnapshots = new Map<string, AgentMessage>()

      for await (const event of stream) {
        if (event.kind === 'error' || event.kind === 'failed') {
          const errorMessage = 'text' in event && typeof event.text === 'string'
            ? event.text
            : 'error' in event && typeof event.error === 'string'
              ? event.error
              : 'Failed to approve plan.'
          if (activeConversationIdRef.current === conversationId) {
            setEvents((currentEvents: EventItem[]) => markWaitingPlanFailed(currentEvents, runtimeId, errorMessage))
          }
        }

        if (event.kind === 'message_update') {
          const message = { ...event, kind: 'message' as const } as unknown as AgentMessage
          if (activeConversationIdRef.current === conversationId) {
            setEvents((currentEvents: EventItem[]) => upsertMessageEvent(currentEvents, message))
          }
          latestMessageSnapshots.set(message.id, message)
          continue
        }

        if (event.kind === 'delta' && event.messageId) {
          const currentText = deltaBuffer.get(event.messageId) || ''
          const newText = currentText + event.text
          deltaBuffer.set(event.messageId, newText)
          if (activeConversationIdRef.current === conversationId) {
            deltaBatcher.push({
              messageId: event.messageId,
              text: newText,
              stage: 'stage' in event ? event.stage : undefined,
            })
          }
          continue
        }

        if (activeConversationIdRef.current === conversationId) {
          setEvents((currentEvents: EventItem[]) => upsertStreamEvent(currentEvents, event))
        }
        pendingPersistEvents.push(event)
        if (isTerminalStreamEvent(event) && activeConversationIdRef.current === conversationId) {
          setEvents((currentEvents: EventItem[]) => finalizeOpenPartialMessages(currentEvents))
        }
      }

      deltaBatcher.flush()

      const finalMessageSnapshots = finalizeOpenPartialMessages(Array.from(latestMessageSnapshots.values()) as EventItem[])
      const finalEvents = flushDeltaBuffer(deltaBuffer, latestEventsRef.current)
      const allPersistEvents = mergeEventsBySequence([...pendingPersistEvents, ...finalMessageSnapshots, ...finalEvents])
      if (allPersistEvents.length > 0) {
        const response = await appendConversationEvents(conversationId, allPersistEvents)
        upsertConversationSummary(response.conversation)
      }
      await syncConversationRuntimes(conversationId)
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to approve plan.'
      setLoadError(errorMessage)
      const errorEvent: EventItem = {
        id: `plan-approval-error-${Date.now()}`,
        kind: 'error',
        text: errorMessage,
      }
      if (activeConversationIdRef.current === conversationId) {
        setEvents((currentEvents: EventItem[]) => upsertStreamEvent(currentEvents, errorEvent))
      }
      try {
        const response = await appendConversationEvents(conversationId, [errorEvent])
        upsertConversationSummary(response.conversation)
        await syncConversationRuntimes(conversationId)
      } catch {
        // Keep loadError as the visible fallback if persisting the error also fails.
      }
    }
  }, [activeConversationId, activeConversationIdRef, setEvents, setLoadError, syncConversationRuntimes, upsertConversationSummary])

  return {
    pendingApprovalRuntimeId,
    backgroundRun,
    activeBackgroundRun,
    clearBackgroundRunUnread,
    runAgent,
    approveRun: (allowPrefix?: string, terminalId?: string | null) => void submitApproval(true, { allowPrefix, terminalId }),
    rejectRun: (terminalId?: string | null) => void submitApproval(false, { terminalId }),
    approvePlanRun,
    decideTerminalAccess,
  }
}
