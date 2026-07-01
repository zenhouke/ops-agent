import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from 'react'
import { appendConversationEvents, streamApproveAgent, streamDecideTerminalRequest, streamRunAgent } from '../../api'
import type { RunMode } from '../../types/api'
import type { AgentMessage, Asset, ConversationContextStatus, ConversationSummary, EventItem, RuntimeSummary } from '../../types/ops'
import { flushDeltaBuffer, LOCAL_TERMINAL_ASSET_ID, mergeDeltaEvent, mergeEventsBySequence, PENDING_ASSISTANT_MESSAGE_ID, upsertMessageEvent, upsertStreamEvent } from './consoleShared'

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
}

type DeltaBatchItem = {
  messageId: string
  text: string
  stage?: string
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
  if (event.kind === 'approval_required' || event.kind === 'approval_decision' || event.kind === 'approval_granted' || event.kind === 'approval_rejected') {
    return event.stepId || `${event.runtimeId || 'runtime'}:${event.command}`
  }
  if ('type' in event && (event.type === 'ask' || (event.type === 'say' && event.say === 'tool_use'))) {
    const runtimeId = (event as any).runtimeId
    const command = event.toolCall?.command || (event.toolCall?.args ? JSON.stringify(event.toolCall.args) : event.text || '')
    return `${runtimeId || 'runtime'}:${command}`
  }
  return null
}

function derivePendingApprovalState(events: EventItem[]): PendingApprovalState | null {
  const settledApprovalKeys = new Set<string>()

  for (let index = events.length - 1; index >= 0; index--) {
    const event = events[index]
    const approvalKey = getApprovalKey(event)

    if (approvalKey && (event.kind === 'approval_decision' || event.kind === 'approval_granted' || event.kind === 'approval_rejected' || ('type' in event && event.type === 'say' && event.say === 'tool_use'))) {
      settledApprovalKeys.add(approvalKey)
      continue
    }

    if (approvalKey && settledApprovalKeys.has(approvalKey)) {
      continue
    }

    if (approvalKey && event.kind === 'approval_required' && event.status !== 'approved' && event.status !== 'rejected' && event.runtimeId) {
      return { runtimeId: event.runtimeId, approvalToken: event.approvalToken ?? null, approvalKey }
    }

    if (approvalKey && 'type' in event && event.type === 'ask') {
      const runtimeId = (event as any).runtimeId
      if (runtimeId) {
        return { runtimeId, approvalToken: event.toolCall?.approvalToken ?? null, approvalKey }
      }
    }
  }

  return null
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

      for await (const event of stream) {
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
            const runtimeId = (event as any).runtimeId
            if (runtimeId) {
              setBackgroundRun((currentRun) => currentRun?.conversationId === conversationId ? { ...currentRun, status: 'needs_approval', hasUnread: !isViewingRunConversation } : currentRun)
              if (isViewingRunConversation) {
                setPendingApprovalRuntimeId(runtimeId)
                setPendingApprovalToken(message.toolCall?.approvalToken ?? null)
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

        if (event.kind === 'approval_required') {
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

      // Batch persist: only the latest snapshot per message, plus non-delta events
      const finalMessageSnapshots = Array.from(latestMessageSnapshots.values()) as EventItem[]
      const finalEvents = flushDeltaBuffer(deltaBuffer, latestEventsRef.current)
      const allPersistEvents = mergeEventsBySequence([...pendingPersistEvents, ...finalMessageSnapshots, ...finalEvents])
      if (allPersistEvents.length > 0) {
        const response = await appendConversationEvents(conversationId, allPersistEvents)
        upsertConversationSummary(response.conversation)
      }
      await syncConversationRuntimes(conversationId)
      setBackgroundRun((currentRun) => currentRun?.conversationId === conversationId ? { ...currentRun, status: 'completed', hasUnread: activeConversationIdRef.current !== conversationId } : currentRun)
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

        for await (const event of stream) {
          if (event.kind === 'message_update') {
            const message = { ...event, kind: 'message' as const } as unknown as AgentMessage
            setEvents((currentEvents: EventItem[]) => upsertMessageEvent(currentEvents, message))

            if (message.type === 'ask' && activeConversationIdRef.current === conversationId) {
              const eventRuntimeId = (event as any).runtimeId
              if (eventRuntimeId) {
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

          // Immediately update UI with transient event, don't block SSE stream
          if (activeConversationIdRef.current === conversationId) {
            setEvents((currentEvents: EventItem[]) => upsertStreamEvent(currentEvents, event))
          }

          // Collect non-delta events, batch persist after stream ends
          pendingPersistEvents.push(event)

          if (event.kind === 'approval_required' && activeConversationIdRef.current === conversationId) {
            setPendingApprovalRuntimeId(event.runtimeId ?? null)
            setPendingApprovalToken(event.approvalToken ?? null)
          }
          if (event.kind === 'approval_decision' && activeConversationIdRef.current === conversationId) {
            setPendingApprovalRuntimeId(null)
            setPendingApprovalToken(null)
          }
        }

        deltaBatcher.flush()

        // Batch persist all non-delta events + message snapshots + delta buffer after stream ends
        const finalMessageSnapshots = Array.from(latestMessageSnapshots.values()) as EventItem[]
        const finalEvents = flushDeltaBuffer(deltaBuffer, latestEventsRef.current)
        const allPersistEvents = mergeEventsBySequence([...pendingPersistEvents, ...finalMessageSnapshots, ...finalEvents])
        if (allPersistEvents.length > 0) {
          const response = await appendConversationEvents(conversationId, allPersistEvents)
          upsertConversationSummary(response.conversation)
        }
        await syncConversationRuntimes(conversationId)
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
      }

      deltaBatcher.flush()

      const finalMessageSnapshots = Array.from(latestMessageSnapshots.values()) as EventItem[]
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

  return {
    pendingApprovalRuntimeId,
    backgroundRun,
    activeBackgroundRun,
    clearBackgroundRunUnread,
    runAgent,
    approveRun: (allowPrefix?: string) => void submitApproval(true, allowPrefix),
    rejectRun: () => void submitApproval(false),
    decideTerminalAccess,
  }
}
