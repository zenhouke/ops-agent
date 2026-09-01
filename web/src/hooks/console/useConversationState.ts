import { useCallback, useEffect, useRef, useState } from 'react'
import {
  appendConversationEvents,
  rewriteConversation as rewriteConversationApi,
  createConversation as createConversationApi,
  deleteConversation as deleteConversationApi,
  getConversationContext,
  getConversationEventsPage,
  getConversationEventsTail,
  getConversations,
  getRuntimeSnapshot,
  listConversationRuntimes,
} from '../../api'
import type { ConversationContextStatus, ConversationSummary, EventItem, RuntimeSnapshot, RuntimeSummary } from '../../types/ops'
import { upsertConversationSummary, upsertStreamEvent } from './consoleShared'

const CONVERSATION_EVENTS_PAGE_SIZE = 200

type ConversationEventWindow = {
  offset: number
  total: number
  hasMoreBefore: boolean
  hasMoreAfter: boolean
}

function terminalSnapshotEvents(snapshot: RuntimeSnapshot | null): EventItem[] {
  if (!snapshot) return []
  return [
    ...(snapshot.runState === 'interrupted' && snapshot.errorMessage ? [{
      id: `snapshot:runtime-interrupted:${snapshot.runtimeId}`,
      kind: 'error' as const,
      text: snapshot.errorMessage,
    }] : []),
    ...snapshot.terminalRequests.map((request): EventItem => ({
      id: `snapshot:terminal-request:${request.requestId}`,
      kind: 'terminal_session_request',
      eventId: `snapshot:terminal-request:${request.requestId}`,
      sequence: snapshot.lastSequence,
      occurredAt: request.expiresAt,
      runtimeId: request.runtimeId,
      requestId: request.requestId,
      assetId: request.assetId,
      assetName: request.assetName,
      reason: request.reason,
      approvalToken: request.approvalToken,
      terminalCreationStatus: request.terminalCreationStatus,
      userDecisionStatus: request.userDecisionStatus,
      scopeExpansionRequired: request.scopeExpansionRequired,
    })),
    ...snapshot.terminalAuthorizations.map((authorization): EventItem => ({
      id: `snapshot:terminal-authorization:${authorization.authorizationId}:${authorization.status}`,
      kind: authorization.status === 'active' ? 'terminal_session_opened' : 'terminal_authorization_revoked',
      eventId: `snapshot:terminal-authorization:${authorization.authorizationId}:${authorization.status}`,
      sequence: snapshot.lastSequence,
      occurredAt: snapshot.updatedAt,
      runtimeId: authorization.runtimeId,
      authorizationId: authorization.authorizationId,
      assetId: authorization.assetId,
      assetName: authorization.assetName,
      terminalId: authorization.terminalId,
      requestId: authorization.requestId,
      reason: authorization.revokeReason ?? authorization.status,
      revokeReason: authorization.revokeReason ?? undefined,
    })),
  ]
}

function mergeSnapshotTerminalEvents(events: EventItem[], snapshot: RuntimeSnapshot | null): EventItem[] {
  const snapshotEvents = terminalSnapshotEvents(snapshot)
  const snapshotIds = new Set(snapshotEvents.map((event) => event.id))
  const currentEvents = events.filter((event) => !snapshotIds.has(event.id))
  return snapshotEvents.reduce(
    (nextEvents, event) => upsertStreamEvent(nextEvents, event),
    currentEvents,
  )
}

function isTerminalRuntime(runtime: RuntimeSummary): boolean {
  const status = runtime.status.toLowerCase()
  return runtime.runState === 'terminal'
    || runtime.runState === 'interrupted'
    || status.includes('complete')
    || status.includes('fail')
    || status.includes('error')
    || status.includes('cancel')
    || status.includes('interrupt')
}

function settleTerminalRuntimeMessages(events: EventItem[], runtimes: RuntimeSummary[]): EventItem[] {
  const terminalRuntimeIds = new Set(
    runtimes.filter(isTerminalRuntime).map((runtime) => runtime.runtimeId)
  )
  if (terminalRuntimeIds.size === 0) return events

  return events.map((event) =>
    event.kind === 'message' && event.partial && event.runtimeId && terminalRuntimeIds.has(event.runtimeId)
      ? { ...event, partial: false }
      : event
  )
}

function mergePrependedEvents(olderEvents: EventItem[], currentEvents: EventItem[]): EventItem[] {
  const currentIds = new Set(currentEvents.map((event) => event.id))
  return [
    ...olderEvents.filter((event) => !currentIds.has(event.id)),
    ...currentEvents,
  ]
}

export function useConversationState(selectedModel: string) {
  const [conversationSummaries, setConversationSummaries] = useState<ConversationSummary[]>([])
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null)
  const [activeConversationTitle, setActiveConversationTitle] = useState('')
  const [events, setEvents] = useState<EventItem[]>([])
  const [eventWindow, setEventWindow] = useState<ConversationEventWindow | null>(null)
  const [isLoadingOlderEvents, setIsLoadingOlderEvents] = useState(false)
  const [runtimeSummaries, setRuntimeSummaries] = useState<RuntimeSummary[]>([])
  const [activeRuntimeId, setActiveRuntimeId] = useState<string | null>(null)
  const [activeRuntimeSnapshot, setActiveRuntimeSnapshot] = useState<RuntimeSnapshot | null>(null)
  const [contextStatus, setContextStatus] = useState<ConversationContextStatus | null>(null)

  const activeConversationIdRef = useRef<string | null>(null)
  const loadConversationRequestRef = useRef(0)

  useEffect(() => {
    activeConversationIdRef.current = activeConversationId
  }, [activeConversationId])

  const loadConversation = useCallback(async (conversationId: string) => {
    const requestId = loadConversationRequestRef.current + 1
    loadConversationRequestRef.current = requestId
    activeConversationIdRef.current = conversationId
    setContextStatus(null)

    const page = await getConversationEventsTail(conversationId, CONVERSATION_EVENTS_PAGE_SIZE)
    if (loadConversationRequestRef.current !== requestId) {
      return page.conversation
    }
    setActiveConversationId(page.conversation.id)
    setActiveConversationTitle(page.conversation.title)
    setEvents(page.events)
    setEventWindow({
      offset: page.offset,
      total: page.total,
      hasMoreBefore: page.hasMoreBefore,
      hasMoreAfter: page.hasMoreAfter,
    })

    const [runtimes, nextContextStatus] = await Promise.all([
      listConversationRuntimes(conversationId),
      getConversationContext(conversationId),
    ])
    if (loadConversationRequestRef.current !== requestId) {
      return page.conversation
    }
    setContextStatus(nextContextStatus)
    setRuntimeSummaries(runtimes)
    const nextRuntimeId = runtimes[0]?.runtimeId ?? null
    setActiveRuntimeId(nextRuntimeId)
    const nextRuntimeSnapshot = nextRuntimeId ? await getRuntimeSnapshot(nextRuntimeId) : null
    if (loadConversationRequestRef.current !== requestId) {
      return page.conversation
    }
    setActiveRuntimeSnapshot(nextRuntimeSnapshot)
    setEvents((currentEvents) => mergeSnapshotTerminalEvents(
      settleTerminalRuntimeMessages(currentEvents, runtimes),
      nextRuntimeSnapshot,
    ))
    return page.conversation
  }, [])

  const refreshConversationList = useCallback(async () => {
    const items = await getConversations()
    setConversationSummaries(items)
    return items
  }, [])

  const applyConversationSummaryIfActive = useCallback((summary: ConversationSummary) => {
    if (activeConversationIdRef.current !== summary.id) {
      return
    }
    setActiveConversationTitle(summary.title)
    setEventWindow((currentWindow) => currentWindow ? {
      ...currentWindow,
      total: summary.eventCount,
      hasMoreBefore: currentWindow.offset > 0,
      hasMoreAfter: currentWindow.offset + events.length < summary.eventCount,
    } : currentWindow)
  }, [events.length])

  const loadOlderConversationEvents = useCallback(async () => {
    const conversationId = activeConversationIdRef.current
    if (!conversationId || !eventWindow?.hasMoreBefore || isLoadingOlderEvents) {
      return
    }
    setIsLoadingOlderEvents(true)
    try {
      const nextOffset = Math.max(0, eventWindow.offset - CONVERSATION_EVENTS_PAGE_SIZE)
      const nextLimit = eventWindow.offset - nextOffset
      const page = await getConversationEventsPage(conversationId, nextOffset, nextLimit)
      if (activeConversationIdRef.current !== conversationId) {
        return
      }
      setEvents((currentEvents) => mergePrependedEvents(
        settleTerminalRuntimeMessages(page.events, runtimeSummaries),
        currentEvents,
      ))
      setEventWindow({
        offset: page.offset,
        total: page.total,
        hasMoreBefore: page.hasMoreBefore,
        hasMoreAfter: page.hasMoreAfter || eventWindow.hasMoreAfter,
      })
    } finally {
      setIsLoadingOlderEvents(false)
    }
  }, [eventWindow, isLoadingOlderEvents, runtimeSummaries])

  const syncConversationRuntimes = useCallback(async (conversationId: string) => {
    const runtimes = await listConversationRuntimes(conversationId)
    if (activeConversationIdRef.current !== conversationId) {
      return runtimes
    }
    setRuntimeSummaries(runtimes)
    const nextRuntimeId = runtimes[0]?.runtimeId ?? null
    setActiveRuntimeId(nextRuntimeId)
    const nextSnapshot = nextRuntimeId ? await getRuntimeSnapshot(nextRuntimeId) : null
    if (activeConversationIdRef.current !== conversationId) {
      return runtimes
    }
    setActiveRuntimeSnapshot(nextSnapshot)
    setEvents((currentEvents) => mergeSnapshotTerminalEvents(
      settleTerminalRuntimeMessages(currentEvents, runtimes),
      nextSnapshot,
    ))
    return runtimes
  }, [])

  const createConversation = useCallback(async (
    assetId = 0,
    scopeMode: 'single' | 'multi' = 'single',
    allowedAssetIds: number[] = [assetId],
  ) => {
    const created = await createConversationApi(selectedModel || null, assetId, scopeMode, allowedAssetIds)
    setConversationSummaries((currentItems) => {
      const nextItems = currentItems.filter((item) => item.id !== created.conversation.id)
      return [created.conversation, ...nextItems]
    })
    activeConversationIdRef.current = created.conversation.id
    setActiveConversationId(created.conversation.id)
    setActiveConversationTitle(created.conversation.title)
    setEvents(created.events)
    setEventWindow({ offset: 0, total: 0, hasMoreBefore: false, hasMoreAfter: false })
    setRuntimeSummaries([])
    setActiveRuntimeId(null)
    setActiveRuntimeSnapshot(null)
    setContextStatus(null)
    return created.conversation.id
  }, [selectedModel])

  const rewriteConversation = useCallback(async (conversationId: string, beforeEventId: string) => {
    const rewritten = await rewriteConversationApi(conversationId, beforeEventId)
    setConversationSummaries((currentItems) => [
      rewritten.conversation,
      ...currentItems.filter((item) => item.id !== rewritten.conversation.id),
    ])
    activeConversationIdRef.current = rewritten.conversation.id
    setActiveConversationId(rewritten.conversation.id)
    setActiveConversationTitle(rewritten.conversation.title)
    setEvents(rewritten.events)
    setEventWindow({ offset: 0, total: rewritten.events.length, hasMoreBefore: false, hasMoreAfter: false })
    setRuntimeSummaries([])
    setActiveRuntimeId(null)
    setActiveRuntimeSnapshot(null)
    setContextStatus(null)
    return rewritten.conversation.id
  }, [])

  const deleteConversation = useCallback(
    async (conversationId: string, replacementAssetId = 0, cancelActive = false) => {
      await deleteConversationApi(conversationId, cancelActive)
      const remainingItems = await refreshConversationList()

      if (remainingItems.length === 0) {
        await createConversation(replacementAssetId)
        return
      }

      if (activeConversationIdRef.current !== conversationId) {
        return
      }

      await loadConversation(remainingItems[0].id)
    },
    [createConversation, loadConversation, refreshConversationList]
  )

  const setActiveConversationMeta = useCallback((id: string, title: string) => {
    setActiveConversationId(id)
    setActiveConversationTitle(title)
  }, [])

  const upsertConversationSummaryState = useCallback(
    (summary: ConversationSummary) => {
      setConversationSummaries((currentItems) =>
        upsertConversationSummary(currentItems, summary)
      )
      applyConversationSummaryIfActive(summary)
    },
    [applyConversationSummaryIfActive]
  )

  return {
    conversationSummaries,
    activeConversationId,
    activeConversationIdRef,
    activeConversationTitle,
    events,
    eventWindow,
    isLoadingOlderEvents,
    setEvents,
    runtimeSummaries,
    activeRuntimeId,
    activeRuntimeSnapshot,
    contextStatus,
    setContextStatus,
    loadConversation,
    syncConversationRuntimes,
    refreshConversationList,
    createConversation,
    rewriteConversation,
    deleteConversation,
    loadOlderConversationEvents,
    setActiveConversationMeta,
    upsertConversationSummary: upsertConversationSummaryState,
  }
}
