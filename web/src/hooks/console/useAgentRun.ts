import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { appendConversationEvents, cancelAgentRuntime, getRuntimeSnapshot, listConversationRuntimes, streamApproveAgent, streamReconnectRuntime, streamRunAgent, streamRuntimeMessage } from '../../api'
import type { AgentMessage, EventItem, RuntimeSummary } from '../../types/ops'
import { finalizeStreamMessages, flushDeltaBuffer, LOCAL_TERMINAL_ASSET_ID, mergeEventsBySequence, PENDING_ASSISTANT_MESSAGE_ID, upsertMessageEvent, upsertStreamEvent } from './consoleShared'
import { createDeltaBatcher, derivePendingApprovalState, getRunErrorMessage, isAbortError, type BackgroundRunState, type BackgroundRunStatus, type ConversationSaveStatus, type UseAgentRunProps } from './agentRunSupport'
import { useTerminalRequestDecision } from './useTerminalRequestDecision'

type RunRegistry = Record<string, BackgroundRunState>
const ACTIVE_RUN_STATUSES: ReadonlySet<BackgroundRunStatus> = new Set(['running', 'needs_approval', 'needs_input', 'disconnected'])

function createUserEventId(): string {
  const bytes = new Uint8Array(16)
  const cryptoApi = globalThis.crypto
  if (cryptoApi && typeof cryptoApi.getRandomValues === 'function') {
    cryptoApi.getRandomValues(bytes)
  } else {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256)
    }
  }
  return `user-${Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')}`
}

function runtimeStatus(runtime: RuntimeSummary): BackgroundRunStatus {
  const status = runtime.status.toLowerCase()
  if (status === 'waiting_user_input') return 'needs_input'
  if (runtime.pendingApprovalStepId || runtime.runState === 'waiting' || status.includes('approv') || status.includes('waiting')) return 'needs_approval'
  if (runtime.runState === 'terminal' || status.includes('complete') || status.includes('fail') || status.includes('error')) {
    return status.includes('fail') || status.includes('error') ? 'failed' : 'completed'
  }
  return 'running'
}

export function useAgentRun({
  conversationSummaries, activeConversationId, activeConversationTitle, activeConversationIdRef, events, setEvents,
  createConversation, loadConversation, upsertConversationSummary, refreshConversationList,
  syncConversationRuntimes, selectedAsset, activeTerminalTab, selectedModel, setLoadError, setContextStatus,
}: UseAgentRunProps) {
  const [runsByConversation, setRunsByConversation] = useState<RunRegistry>({})
  const runsRef = useRef<RunRegistry>({})
  const abortControllersRef = useRef(new Map<string, AbortController>())
  const intentionalCancellationsRef = useRef(new Set<string>())
  const submittedApprovalKeysRef = useRef(new Map<string, string>())
  const eventCacheRef = useRef(new Map<string, EventItem[]>())
  const runtimeHydrationRef = useRef(new Map<string, string>())
  const latestEventsRef = useRef<EventItem[]>(events)

  const updateRun = useCallback((conversationId: string, updater: (run?: BackgroundRunState) => BackgroundRunState | undefined) => {
    setRunsByConversation((current) => {
      const nextRun = updater(current[conversationId])
      if (nextRun === current[conversationId]) return current
      const next = { ...current }
      if (nextRun) next[conversationId] = nextRun
      else delete next[conversationId]
      runsRef.current = next
      return next
    })
  }, [])

  const updateVisibleEvents = useCallback((conversationId: string, updater: (current: EventItem[]) => EventItem[]) => {
    if (activeConversationIdRef.current !== conversationId) return
    setEvents((current) => {
      if (activeConversationIdRef.current !== conversationId) return current
      const next = updater(current)
      eventCacheRef.current.set(conversationId, next)
      return next
    })
  }, [activeConversationIdRef, setEvents])

  const markUnread = useCallback((conversationId: string) => {
    if (activeConversationIdRef.current !== conversationId) {
      updateRun(conversationId, (run) => run && !run.hasUnread ? { ...run, hasUnread: true } : run)
    }
  }, [activeConversationIdRef, updateRun])

  const updateRunSaveStatus = useCallback((conversationId: string, status: ConversationSaveStatus) => {
    updateRun(conversationId, (run) => run && run.saveStatus !== status ? { ...run, saveStatus: status } : run)
  }, [updateRun])

  const observePersistenceStatus = useCallback((conversationId: string, event: EventItem) => {
    if ((event as EventItem & { persistenceStatus?: string }).persistenceStatus === 'failed') updateRunSaveStatus(conversationId, 'failed')
  }, [updateRunSaveStatus])

  useEffect(() => {
    latestEventsRef.current = events
    if (activeConversationId) eventCacheRef.current.set(activeConversationId, events)
  }, [activeConversationId, events])

  useEffect(() => {
    if (!activeConversationId) return
    const pending = derivePendingApprovalState(events)
    if (!pending || submittedApprovalKeysRef.current.get(activeConversationId) === pending.approvalKey) return
    submittedApprovalKeysRef.current.delete(activeConversationId)
    updateRun(activeConversationId, (run) => ({
      conversationId: activeConversationId,
      title: run?.title ?? (activeConversationTitle || '当前会话'),
      assetId: run?.assetId ?? selectedAsset.id,
      assetName: run?.assetName ?? selectedAsset.name,
      runtimeId: pending.runtimeId,
      status: 'needs_approval', hasUnread: false,
      pendingApprovalToken: pending.approvalToken ?? run?.pendingApprovalToken ?? null,
      pendingApprovalKey: pending.approvalKey,
      saveStatus: run?.saveStatus ?? 'saved',
    }))
  }, [activeConversationId, activeConversationTitle, events, selectedAsset.id, selectedAsset.name, updateRun])

  useEffect(() => {
    let cancelled = false
    void (async () => {
      const candidates = conversationSummaries.filter((summary) => runtimeHydrationRef.current.get(summary.id) !== summary.updatedAt)
      await Promise.all(candidates.map(async (summary) => {
        runtimeHydrationRef.current.set(summary.id, summary.updatedAt)
        try {
          const runtimes = await listConversationRuntimes(summary.id)
          const runtime = runtimes.find((item) => item.runState !== 'terminal')
          if (!runtime || cancelled) return
          const status = runtimeStatus(runtime)
          const snapshot = status === 'needs_approval' || status === 'needs_input' ? await getRuntimeSnapshot(runtime.runtimeId) : null
          if (cancelled) return
          updateRun(summary.id, (run) => ({
            conversationId: summary.id,
            title: summary.title || run?.title || '未命名会话',
            assetId: runtime.assetId,
            assetName: run?.assetName ?? (runtime.assetId === selectedAsset.id ? selectedAsset.name : `资产 #${runtime.assetId}`),
            runtimeId: runtime.runtimeId, status,
            hasUnread: run?.hasUnread ?? activeConversationIdRef.current !== summary.id,
            pendingApprovalToken: snapshot?.pendingApprovalToken ?? run?.pendingApprovalToken ?? null,
            pendingApprovalKey: run?.pendingApprovalKey ?? runtime.pendingApprovalStepId,
            saveStatus: run?.saveStatus ?? 'saved',
          }))
        } catch { /* Runtime hydration is best-effort. */ }
      }))
    })()
    return () => { cancelled = true }
  }, [activeConversationIdRef, conversationSummaries, selectedAsset.id, selectedAsset.name, updateRun])

  const clearRunUnread = useCallback((conversationId: string) => {
    updateRun(conversationId, (run) => run?.hasUnread ? { ...run, hasUnread: false } : run)
  }, [updateRun])

  useEffect(() => { if (activeConversationId) clearRunUnread(activeConversationId) }, [activeConversationId, clearRunUnread])

  const processStream = useCallback(async (conversationId: string, stream: AsyncGenerator<EventItem, void, void>) => {
    const deltaBuffer = new Map<string, string>()
    const batcher = createDeltaBatcher({ setEvents, isActive: () => activeConversationIdRef.current === conversationId })
    const persisted: EventItem[] = []
    const messages = new Map<string, AgentMessage>()
    let runtimeId = runsRef.current[conversationId]?.runtimeId ?? null
    let lastSequence = 0
    let requiresApproval = false
    let requiresInput = false
    let runtimeFailed = false
    try {
      for await (const event of stream) {
        observePersistenceStatus(conversationId, event)
        const eventRuntimeId = (event as EventItem & { runtimeId?: string }).runtimeId
        if (eventRuntimeId) {
          runtimeId = eventRuntimeId
          updateRun(conversationId, (run) => run ? { ...run, runtimeId: eventRuntimeId } : run)
        }
        const sequence = (event as EventItem & { sequence?: number }).sequence
        if (typeof sequence === 'number' && sequence > lastSequence) lastSequence = sequence

        if (event.kind === 'message_update') {
          const message = { ...event, kind: 'message' as const } as unknown as AgentMessage
          updateVisibleEvents(conversationId, (current) => upsertMessageEvent(current, message))
          markUnread(conversationId)
          if (message.type === 'ask' && eventRuntimeId) {
            const needsFollowup = message.ask === 'followup'
            requiresApproval = !needsFollowup
            requiresInput = needsFollowup
            const pending = derivePendingApprovalState([message])
            updateRun(conversationId, (run) => run ? {
              ...run, runtimeId: eventRuntimeId, status: needsFollowup ? 'needs_input' : 'needs_approval',
              hasUnread: activeConversationIdRef.current !== conversationId,
              pendingApprovalToken: needsFollowup ? null : message.toolCall?.approvalToken ?? null,
              pendingApprovalKey: needsFollowup ? null : pending?.approvalKey ?? null,
            } : run)
          }
          messages.set(message.id, message)
          continue
        }
        if (event.kind === 'delta' && event.messageId) {
          const text = `${deltaBuffer.get(event.messageId) || ''}${event.text}`
          deltaBuffer.set(event.messageId, text)
          if (activeConversationIdRef.current === conversationId) batcher.push({ messageId: event.messageId, text, stage: 'stage' in event ? event.stage : undefined })
          else markUnread(conversationId)
          continue
        }
        if (event.kind === 'context_status') {
          if (activeConversationIdRef.current === conversationId) {
            setContextStatus((current) => ({
              contextPercent: event.contextPercent ?? current?.contextPercent ?? 0,
              contextStatus: event.contextStatus ?? current?.contextStatus ?? 'normal',
              tokenUsage: event.tokenUsage ?? current?.tokenUsage,
              knowledgeEntriesInjected: event.knowledgeEntriesInjected ?? current?.knowledgeEntriesInjected,
              knowledgeContextChars: event.knowledgeContextChars ?? current?.knowledgeContextChars,
            }))
          }
          continue
        }
        updateVisibleEvents(conversationId, (current) => upsertStreamEvent(current, event))
        markUnread(conversationId)
        persisted.push(event)
        if (event.kind === 'error') runtimeFailed = true
        if (event.kind === 'task_state' && activeConversationIdRef.current === conversationId) {
          await syncConversationRuntimes(conversationId)
        } else if (event.kind === 'approval_required') {
          requiresApproval = true
          const pending = derivePendingApprovalState([event])
          updateRun(conversationId, (run) => run ? {
            ...run, runtimeId: event.runtimeId ?? run.runtimeId, status: 'needs_approval',
            hasUnread: activeConversationIdRef.current !== conversationId,
            pendingApprovalToken: event.approvalToken ?? null, pendingApprovalKey: pending?.approvalKey ?? null,
          } : run)
        } else if (event.kind === 'terminal_session_request' && event.userDecisionStatus !== 'approved' && event.userDecisionStatus !== 'rejected') {
          requiresApproval = true
          updateRun(conversationId, (run) => run ? { ...run, status: 'needs_approval', hasUnread: activeConversationIdRef.current !== conversationId } : run)
        } else if (event.kind === 'approval_decision' || event.kind === 'approval_granted' || event.kind === 'approval_rejected') {
          updateRun(conversationId, (run) => run ? { ...run, pendingApprovalToken: null, pendingApprovalKey: null } : run)
        }
      }
      batcher.flush()
      const finalizedMessages = finalizeStreamMessages(messages.values(), deltaBuffer, runtimeFailed)
      const finalizedMessageIds = new Set(finalizedMessages.map((message) => message.id))
      const finalEvents = mergeEventsBySequence([
        ...persisted,
        ...finalizedMessages as EventItem[],
        ...flushDeltaBuffer(deltaBuffer, eventCacheRef.current.get(conversationId) ?? [], finalizedMessageIds),
      ])
      if (finalEvents.length > 0) {
        const response = await appendConversationEvents(conversationId, finalEvents)
        upsertConversationSummary(response.conversation)
      }
      updateRunSaveStatus(conversationId, 'saved')
      let status: BackgroundRunStatus = runtimeFailed ? 'failed' : requiresInput ? 'needs_input' : requiresApproval ? 'needs_approval' : 'completed'
      if (runtimeId) {
        try {
          const runtime = (await listConversationRuntimes(conversationId)).find((item) => item.runtimeId === runtimeId)
          if (runtime) status = runtimeStatus(runtime)
        } catch { /* Fall back to the terminal event state when snapshot refresh fails. */ }
      }
      updateRun(conversationId, (run) => run ? {
        ...run, status, hasUnread: activeConversationIdRef.current !== conversationId,
        pendingApprovalToken: requiresApproval ? run.pendingApprovalToken : null,
        pendingApprovalKey: requiresApproval ? run.pendingApprovalKey : null,
      } : run)
      if (activeConversationIdRef.current === conversationId) await syncConversationRuntimes(conversationId)
      return { runtimeId, lastSequence, status }
    } finally { batcher.cancel() }
  }, [activeConversationIdRef, markUnread, observePersistenceStatus, setContextStatus, setEvents, syncConversationRuntimes, updateRun, updateRunSaveStatus, updateVisibleEvents, upsertConversationSummary])

  const recoverRuntime = useCallback(async (conversationId: string, runtimeId: string, since: number) => {
    const delays = [0, 250, 750]
    for (const delay of delays) {
      if (delay) await new Promise((resolve) => window.setTimeout(resolve, delay))
      try {
        const reconnectStream = await streamReconnectRuntime(runtimeId, since)
        for await (const event of reconnectStream) observePersistenceStatus(conversationId, event)
        const runtime = (await listConversationRuntimes(conversationId)).find((item) => item.runtimeId === runtimeId)
        if (!runtime) continue
        const status = runtimeStatus(runtime)
        const snapshot = status === 'needs_approval' || status === 'needs_input' ? await getRuntimeSnapshot(runtimeId) : null
        if (activeConversationIdRef.current === conversationId) {
          await loadConversation(conversationId)
          await syncConversationRuntimes(conversationId)
        }
        return { status, approvalToken: snapshot?.pendingApprovalToken ?? null }
      } catch (error) { if (delay === delays[delays.length - 1]) throw error }
    }
    return null
  }, [activeConversationIdRef, loadConversation, observePersistenceStatus, syncConversationRuntimes])

  const runAgent = useCallback(async (runPrompt: string, selectedSkillName?: string | null, mode: 'standard' | 'incident' = 'standard') => {
    setLoadError(null)
    let conversationId = activeConversationIdRef.current
    let runtimeId: string | null = null
    let lastSequence = 0
    try {
      const existingRun = conversationId ? runsRef.current[conversationId] : undefined
      if (conversationId && existingRun && ACTIVE_RUN_STATUSES.has(existingRun.status)) {
        if (!existingRun.runtimeId) throw new Error('Agent 运行正在初始化，请稍后再发送补充指令。')
        updateRunSaveStatus(conversationId, 'saving')
        const guidanceStream = await streamRuntimeMessage(existingRun.runtimeId, runPrompt)
        if (existingRun.status === 'needs_input') {
          await processStream(conversationId, guidanceStream)
        } else {
          for await (const event of guidanceStream) {
            observePersistenceStatus(conversationId, event)
            updateVisibleEvents(conversationId, (current) => upsertStreamEvent(current, event))
            if (event.kind === 'task_state' && activeConversationIdRef.current === conversationId) {
              await syncConversationRuntimes(conversationId)
            }
          }
          updateRunSaveStatus(conversationId, 'saved')
        }
        return
      }
      const activeConversation = conversationId
        ? conversationSummaries.find((item) => item.id === conversationId)
        : undefined
      const selectedAssetAllowed = activeConversation?.allowedAssetIds.includes(selectedAsset.id) ?? false
      if (!conversationId || (activeConversation && !selectedAssetAllowed)) {
        conversationId = await createConversation(selectedAsset.id, 'single')
      }
      if (!conversationId) throw new Error('No active conversation available for agent run.')
      updateRun(conversationId, () => ({
        conversationId: conversationId!,
        title: activeConversationId === conversationId ? activeConversationTitle || '当前会话' : '后台会话',
        assetId: selectedAsset.id, assetName: selectedAsset.name, runtimeId: null,
        status: 'running', hasUnread: false, pendingApprovalToken: null, pendingApprovalKey: null, saveStatus: 'saving',
      }))
      const userEventId = createUserEventId()
      updateVisibleEvents(conversationId, (current) => [...current,
        { id: userEventId, kind: 'user', text: runPrompt },
        { id: PENDING_ASSISTANT_MESSAGE_ID, kind: 'delta', messageId: PENDING_ASSISTANT_MESSAGE_ID, stage: 'assistant', text: '正在理解请求并确定下一步…' },
      ])
      const controller = new AbortController()
      abortControllersRef.current.set(conversationId, controller)
      intentionalCancellationsRef.current.delete(conversationId)
      const stream = await streamRunAgent(runPrompt, selectedAsset.id === LOCAL_TERMINAL_ASSET_ID ? undefined : selectedAsset.id, activeTerminalTab?.sessionId ?? null, selectedModel, conversationId, userEventId, selectedSkillName, mode, controller.signal)
      const result = await processStream(conversationId, stream)
      runtimeId = result.runtimeId
      lastSequence = result.lastSequence
    } catch (error) {
      if (!conversationId) { setLoadError(getRunErrorMessage(error)); return }
      if (intentionalCancellationsRef.current.has(conversationId) || isAbortError(error)) {
        updateRun(conversationId, (run) => run ? { ...run, status: 'failed', pendingApprovalToken: null, pendingApprovalKey: null } : run)
        return
      }
      runtimeId = runtimeId ?? runsRef.current[conversationId]?.runtimeId ?? null
      if (runtimeId) {
        try {
          const recovered = await recoverRuntime(conversationId, runtimeId, lastSequence)
          if (recovered) {
            updateRun(conversationId, (run) => run ? { ...run, status: recovered.status, pendingApprovalToken: recovered.approvalToken ?? run.pendingApprovalToken, hasUnread: activeConversationIdRef.current !== conversationId, saveStatus: 'saved' } : run)
            return
          }
        } catch { /* Fall through to disconnected state. */ }
        updateRun(conversationId, (run) => run ? { ...run, status: 'disconnected', hasUnread: activeConversationIdRef.current !== conversationId } : run)
        if (activeConversationIdRef.current === conversationId) setLoadError('流式连接已中断，任务可能仍在后台运行。请稍后重新打开该会话同步状态。')
        return
      }
      const message = getRunErrorMessage(error)
      updateRun(conversationId, (run) => run ? { ...run, status: 'failed', hasUnread: activeConversationIdRef.current !== conversationId, saveStatus: 'failed' } : run)
      const errorEvent: EventItem = { id: `error-${Date.now()}`, kind: 'error', text: message }
      updateVisibleEvents(conversationId, (current) => upsertStreamEvent(current, errorEvent))
      markUnread(conversationId)
      if (activeConversationIdRef.current === conversationId) setLoadError(message)
      try {
        const response = await appendConversationEvents(conversationId, [errorEvent])
        upsertConversationSummary(response.conversation)
        updateRunSaveStatus(conversationId, 'saved')
        if (activeConversationIdRef.current === conversationId) await syncConversationRuntimes(conversationId)
      } catch { updateRunSaveStatus(conversationId, 'failed') }
    } finally {
      if (conversationId) { abortControllersRef.current.delete(conversationId); intentionalCancellationsRef.current.delete(conversationId) }
      try { await refreshConversationList() } catch { /* Best effort. */ }
    }
  }, [activeConversationId, activeConversationIdRef, activeConversationTitle, activeTerminalTab?.sessionId, conversationSummaries, createConversation, markUnread, observePersistenceStatus, processStream, recoverRuntime, refreshConversationList, selectedAsset.id, selectedAsset.name, selectedModel, setLoadError, syncConversationRuntimes, updateRun, updateRunSaveStatus, updateVisibleEvents, upsertConversationSummary])

  const submitApproval = useCallback(async (approved: boolean, allowPrefix?: string, guidance?: string) => {
    if (!activeConversationId) return
    const run = runsRef.current[activeConversationId]
    if (!run?.runtimeId || run.status !== 'needs_approval') return
    const conversationId = activeConversationId
    if (run.pendingApprovalKey) submittedApprovalKeysRef.current.set(conversationId, run.pendingApprovalKey)
    updateRunSaveStatus(conversationId, 'saving')
    updateRun(conversationId, (current) => current ? { ...current, status: 'running', pendingApprovalToken: null, pendingApprovalKey: null } : current)
    updateVisibleEvents(conversationId, (current) => [...current, { id: PENDING_ASSISTANT_MESSAGE_ID, kind: 'delta', messageId: PENDING_ASSISTANT_MESSAGE_ID, stage: 'assistant', text: approved ? '已提交批准，Agent 正在继续…' : '已提交拒绝，Agent 正在根据你的决定调整…' }])
    try {
      await processStream(conversationId, await streamApproveAgent(run.runtimeId, approved, run.pendingApprovalToken ?? undefined, allowPrefix, guidance))
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to submit approval.'
      updateRun(conversationId, (current) => current ? { ...current, status: 'needs_approval', pendingApprovalToken: run.pendingApprovalToken, pendingApprovalKey: run.pendingApprovalKey, saveStatus: 'failed' } : current)
      if (activeConversationIdRef.current === conversationId) setLoadError(message)
      try { upsertConversationSummary((await appendConversationEvents(conversationId, [{ id: `approval-error-${Date.now()}`, kind: 'error', text: message }])).conversation) } catch { /* Retry remains available. */ }
    } finally { try { await refreshConversationList() } catch { /* Best effort. */ } }
  }, [activeConversationId, activeConversationIdRef, processStream, refreshConversationList, setLoadError, updateRun, updateRunSaveStatus, updateVisibleEvents, upsertConversationSummary])

  const cancelRun = useCallback(async () => {
    if (!activeConversationId) return
    const conversationId = activeConversationId
    const run = runsRef.current[conversationId]
    if (!run || !ACTIVE_RUN_STATUSES.has(run.status)) return
    intentionalCancellationsRef.current.add(conversationId)
    updateRunSaveStatus(conversationId, 'saving')
    try {
      if (run.runtimeId) await cancelAgentRuntime(run.runtimeId)
      abortControllersRef.current.get(conversationId)?.abort()
      updateRun(conversationId, (current) => current ? { ...current, status: 'failed', pendingApprovalToken: null, pendingApprovalKey: null, saveStatus: 'saved' } : current)
      const event: EventItem = { id: `runtime-cancelled-${run.runtimeId ?? 'pending'}-${Date.now()}`, kind: 'error', text: '运行已由操作员取消。' }
      updateVisibleEvents(conversationId, (current) => upsertStreamEvent(current, event))
      upsertConversationSummary((await appendConversationEvents(conversationId, [event])).conversation)
      if (activeConversationIdRef.current === conversationId) await syncConversationRuntimes(conversationId)
    } catch (error) {
      intentionalCancellationsRef.current.delete(conversationId)
      updateRunSaveStatus(conversationId, 'failed')
      setLoadError(error instanceof Error ? error.message : '取消运行失败。')
    }
  }, [activeConversationId, activeConversationIdRef, setLoadError, syncConversationRuntimes, updateRun, updateRunSaveStatus, updateVisibleEvents, upsertConversationSummary])

  const activeRun = activeConversationId ? runsByConversation[activeConversationId] : undefined
  const runs = useMemo(() => Object.values(runsByConversation), [runsByConversation])
  const backgroundRuns = useMemo(() => runs.filter((run) => run.conversationId !== activeConversationId && (ACTIVE_RUN_STATUSES.has(run.status) || run.hasUnread)), [activeConversationId, runs])
  const settleRuntime = useCallback(async (conversationId: string, runtimeId: string) => {
    const runtime = (await listConversationRuntimes(conversationId)).find((item) => item.runtimeId === runtimeId)
    if (!runtime) return
    const status = runtimeStatus(runtime)
    const snapshot = status === 'needs_approval' || status === 'needs_input' ? await getRuntimeSnapshot(runtimeId) : null
    updateRun(conversationId, (run) => run ? {
      ...run,
      status,
      pendingApprovalToken: snapshot?.pendingApprovalToken ?? null,
      pendingApprovalKey: runtime.pendingApprovalStepId,
      hasUnread: activeConversationIdRef.current !== conversationId,
    } : run)
  }, [activeConversationIdRef, updateRun])
  const decideTerminalAccess = useTerminalRequestDecision({
    activeConversationId, activeConversationIdRef, latestEventsRef, setEvents, setLoadError,
    syncConversationRuntimes, upsertConversationSummary,
    onPersistenceStatus: observePersistenceStatus,
    setSaveStatus: updateRunSaveStatus,
    onRuntimeSettled: settleRuntime,
  })
  const approveRun = useCallback((allowPrefix?: string, guidance?: string) => void submitApproval(true, allowPrefix, guidance), [submitApproval])
  const rejectRun = useCallback((guidance?: string) => void submitApproval(false, undefined, guidance), [submitApproval])

  return {
    pendingApprovalRuntimeId: activeRun?.pendingApprovalToken ? activeRun.runtimeId : null,
    conversationSaveStatus: activeRun?.saveStatus ?? 'idle',
    runs, backgroundRuns, clearRunUnread,
    activeRunStatus: activeRun?.status ?? null,
    isRunActive: Boolean(activeRun && ACTIVE_RUN_STATUSES.has(activeRun.status)),
    runAgent, cancelRun, approveRun, rejectRun, decideTerminalAccess,
  }
}
