import { useCallback, useMemo, useState } from 'react'
import {
  cancelOrchestration,
  getOrchestrationEvents,
  getOrchestrationSnapshot,
  resolveOrchestrationTargets,
  streamApproveOrchestrationChild,
  streamRunOrchestration,
  type ResolvedOrchestrationTargets,
} from '../../api'
import type {
  Asset,
  EventItem,
  OrchestrationChild,
  OrchestrationChildStatus,
  OrchestrationEvent,
  OrchestrationSnapshot,
  OrchestrationStatus,
} from '../../types/ops'
import { getApprovalKeys, isApprovalSettlingEvent } from '../../utils/approvalState'

type PendingOrchestrationApproval = {
  orchestrationId: string
  runtimeId: string
  assetId: number
  assetName: string
  command: string
  approvalToken: string | null
}

const ORCHESTRATION_REFERENCE_KINDS = new Set([
  'orchestration_started',
  'child_runtime_started',
  'child_runtime_event',
  'child_runtime_status',
  'child_runtime_completed',
  'child_runtime_failed',
  'orchestration_summary',
  'orchestration_needs_approval',
  'orchestration_completed',
  'orchestration_failed',
  'orchestration_cancelled',
])

export type OrchestrationTargetPreview = ResolvedOrchestrationTargets & {
  prompt: string
  assets: Asset[]
  currentAsset: Asset | null
  conversationId: string
  modelName?: string | null
  selectedSkillName?: string | null
  maxConcurrency: number
}

function isOrchestrationEvent(event: EventItem): event is OrchestrationEvent {
  return 'orchestrationId' in event && typeof event.orchestrationId === 'string'
}

function emptySnapshot(event: OrchestrationEvent): OrchestrationSnapshot {
  return {
    orchestrationId: event.orchestrationId,
    conversationId: event.conversationId ?? 'console',
    prompt: '',
    targetAssetIds: event.targetAssetIds ?? [],
    targetSelectionSource: event.targetSelectionSource ?? '',
    targetSelectionReason: event.targetSelectionReason ?? '',
    confidence: event.confidence ?? 'medium',
    status: 'running',
    maxConcurrency: event.maxConcurrency ?? 3,
    children: [],
    finalSummary: null,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    lastSequence: event.sequence ?? 0,
  }
}

function upsertChild(
  children: OrchestrationChild[],
  child: Partial<OrchestrationChild> & { assetId: number; assetName: string },
): OrchestrationChild[] {
  const existing = children.find((item) => item.assetId === child.assetId)
  if (!existing) {
    return [
      ...children,
      {
        assetId: child.assetId,
        assetName: child.assetName,
        runtimeId: child.runtimeId ?? null,
        terminalId: child.terminalId ?? null,
        status: child.status ?? 'pending',
        summary: child.summary ?? '',
        errorMessage: child.errorMessage ?? '',
        lastSequence: child.lastSequence ?? 0,
        events: child.events ?? [],
      },
    ]
  }
  return children.map((item) =>
    item.assetId === child.assetId
      ? {
          ...item,
          ...child,
          events: child.events ?? item.events,
        }
      : item,
  )
}

function upsertChildEvent(events: EventItem[], event: EventItem): EventItem[] {
  if (typeof event.id !== 'string') {
    return [...events, event]
  }
  const existingIndex = events.findIndex((item) => item.id === event.id)
  if (existingIndex < 0) {
    return [...events, event]
  }
  const nextEvents = [...events]
  nextEvents[existingIndex] = event
  return nextEvents
}

function childStatusFromRuntimeEvent(event: EventItem | undefined, fallback: OrchestrationChildStatus): OrchestrationChildStatus {
  if (!event) {
    return fallback
  }
  const kind = event.kind as string
  if (kind === 'message_update') {
    const message = event as any
    if (message.type === 'ask') {
      return 'needs_approval'
    }
    if (message.type === 'say' && message.say === 'tool_use' && fallback === 'needs_approval') {
      return 'running'
    }
    return fallback
  }
  if (kind === 'approval_decision' || kind === 'approval_granted') {
    return 'running'
  }
  if (kind === 'approval_rejected') {
    return 'failed'
  }
  if (kind === 'command_end') {
    const exitCode = (event as any).exitCode
    if (typeof exitCode === 'number' && exitCode !== 0) {
      return 'failed'
    }
    return fallback
  }
  if (kind === 'completed' || kind === 'final' || kind === 'loop_final') {
    if (fallback === 'failed') {
      return fallback
    }
    return 'completed'
  }
  if (kind === 'failed' || kind === 'error' || kind === 'loop_failed' || kind === 'task_failed') {
    return 'failed'
  }
  return fallback
}

function childSummaryFromRuntimeEvent(event: EventItem | undefined, fallback: string): string {
  if (!event) {
    return fallback
  }
  const kind = event.kind as string
  if ('summary' in event && typeof event.summary === 'string') {
    return event.summary
  }
  if ((kind === 'completed' || kind === 'final' || kind === 'loop_final') && 'text' in event && typeof event.text === 'string') {
    return event.text
  }
  return fallback
}

function childErrorFromRuntimeEvent(event: EventItem | undefined, fallback: string): string {
  if (!event) {
    return fallback
  }
  if (event.kind === 'error' && 'text' in event && typeof event.text === 'string') {
    return event.text
  }
  if ((event.kind === 'loop_failed' || event.kind === 'task_failed') && 'error' in event && typeof event.error === 'string') {
    return event.error
  }
  if ('error' in event && typeof event.error === 'string') {
    return event.error
  }
  return fallback
}

function deriveSnapshotStatus(children: OrchestrationChild[], fallback: OrchestrationStatus): OrchestrationStatus {
  if (fallback === 'cancelled') {
    return fallback
  }
  if (children.some((child) => child.status === 'needs_approval')) {
    return 'needs_approval'
  }
  if (children.some((child) => child.status === 'running' || child.status === 'pending')) {
    return 'running'
  }
  const completed = children.filter((child) => child.status === 'completed').length
  const failed = children.filter((child) => child.status === 'failed').length
  if (completed > 0 && failed > 0) {
    return 'partial_failed'
  }
  if (failed > 0 && completed === 0) {
    return 'failed'
  }
  if (completed > 0 && completed === children.length) {
    return 'completed'
  }
  return fallback
}

function applyEvent(snapshot: OrchestrationSnapshot | null, event: EventItem): OrchestrationSnapshot | null {
  if (!isOrchestrationEvent(event)) {
    return snapshot
  }
  const current = snapshot ?? emptySnapshot(event)
  if (current.status === 'cancelled' && event.kind !== 'orchestration_cancelled' && event.kind !== 'orchestration_summary') {
    if (event.kind === 'child_runtime_status' && event.assetId && event.assetName && event.status === 'cancelled') {
      const existing = current.children.find((child) => child.assetId === event.assetId)
      return {
        ...current,
        children: upsertChild(current.children, {
          assetId: event.assetId,
          assetName: event.assetName,
          runtimeId: event.runtimeId ?? existing?.runtimeId ?? null,
          terminalId: event.terminalId ?? existing?.terminalId ?? null,
          status: 'cancelled',
          summary: event.summary ?? existing?.summary ?? '',
          errorMessage: event.errorMessage ?? existing?.errorMessage ?? '',
          lastSequence: event.childSequence ?? existing?.lastSequence ?? 0,
        }),
        lastSequence: event.sequence ?? current.lastSequence,
        updatedAt: new Date().toISOString(),
      }
    }
    return current
  }
  let next: OrchestrationSnapshot = {
    ...current,
    lastSequence: event.sequence ?? current.lastSequence,
    updatedAt: new Date().toISOString(),
  }

  if (event.kind === 'orchestration_started') {
    next = {
      ...next,
      targetAssetIds: event.targetAssetIds ?? next.targetAssetIds,
      targetSelectionSource: event.targetSelectionSource ?? next.targetSelectionSource,
      targetSelectionReason: event.targetSelectionReason ?? next.targetSelectionReason,
      confidence: event.confidence ?? next.confidence,
      maxConcurrency: event.maxConcurrency ?? next.maxConcurrency,
      status: 'running',
    }
  }

  if (event.assetId && event.assetName) {
    const existing = next.children.find((child) => child.assetId === event.assetId)
    const childEvents = event.event ? upsertChildEvent(existing?.events ?? [], event.event) : existing?.events
    const fallbackStatus = (event.status as OrchestrationChildStatus | undefined) ?? existing?.status ?? 'running'
    next = {
      ...next,
      children: upsertChild(next.children, {
        assetId: event.assetId,
        assetName: event.assetName,
        runtimeId: event.runtimeId ?? existing?.runtimeId ?? null,
        terminalId: event.terminalId ?? existing?.terminalId ?? null,
        status: childStatusFromRuntimeEvent(event.event, fallbackStatus),
        summary: event.summary ?? childSummaryFromRuntimeEvent(event.event, existing?.summary ?? ''),
        errorMessage: event.errorMessage ?? childErrorFromRuntimeEvent(event.event, existing?.errorMessage ?? ''),
        lastSequence: event.childSequence ?? existing?.lastSequence ?? 0,
        events: childEvents,
      }),
    }
  }

  if (event.children) {
    next = {
      ...next,
      children: event.children.map((child) => ({
        ...child,
        status: child.status as OrchestrationChildStatus,
        events: next.children.find((item) => item.assetId === child.assetId)?.events ?? [],
      })),
    }
  }

  if (event.kind === 'child_runtime_event' || event.kind === 'child_runtime_status' || event.kind === 'child_runtime_completed' || event.kind === 'child_runtime_failed') {
    next = {
      ...next,
      status: deriveSnapshotStatus(next.children, next.status),
    }
  }

  if (event.finalSummary || event.kind === 'orchestration_summary') {
    next = {
      ...next,
      finalSummary: event.finalSummary ?? next.finalSummary,
      status: (event.status as OrchestrationStatus | undefined) ?? next.status,
    }
  }

  if (
    event.kind === 'orchestration_needs_approval' ||
    event.kind === 'orchestration_completed' ||
    event.kind === 'orchestration_failed' ||
    event.kind === 'orchestration_cancelled'
  ) {
    next = {
      ...next,
      status: (event.status as OrchestrationStatus | undefined) ?? next.status,
      finalSummary: event.finalSummary ?? next.finalSummary,
    }
  }

  return next
}

function latestOrchestrationId(events: EventItem[], conversationId: string): string | null {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index]
    if (!isOrchestrationEvent(event)) {
      continue
    }
    if (!ORCHESTRATION_REFERENCE_KINDS.has(event.kind)) {
      continue
    }
    if (event.conversationId && event.conversationId !== conversationId) {
      continue
    }
    return event.orchestrationId
  }
  return null
}

function replayConversationOrchestration(events: EventItem[], orchestrationId: string): OrchestrationSnapshot | null {
  return events
    .filter((event): event is OrchestrationEvent => isOrchestrationEvent(event) && event.orchestrationId === orchestrationId)
    .reduce<OrchestrationSnapshot | null>((currentSnapshot, event) => applyEvent(currentSnapshot, event), null)
}

function hasReplayableProgress(snapshot: OrchestrationSnapshot | null): snapshot is OrchestrationSnapshot {
  if (!snapshot) {
    return false
  }
  return (
    snapshot.lastSequence > 1 ||
    Boolean(snapshot.finalSummary) ||
    snapshot.children.some((child) => child.events.length > 0 || child.status !== 'pending')
  )
}

function isTerminalOrchestrationStatus(status: OrchestrationStatus): boolean {
  return status === 'completed' || status === 'partial_failed' || status === 'failed' || status === 'cancelled'
}

function derivePendingApprovals(snapshot: OrchestrationSnapshot | null): PendingOrchestrationApproval[] {
  if (!snapshot) {
    return []
  }
  const approvals: PendingOrchestrationApproval[] = []
  for (const child of snapshot.children) {
    if (child.status !== 'needs_approval') {
      continue
    }
    const settledApprovalKeys = new Set<string>()
    for (let index = child.events.length - 1; index >= 0; index -= 1) {
      const event = child.events[index]
      const approvalKeys = getApprovalKeys(event)
      if (approvalKeys.length > 0 && isApprovalSettlingEvent(event)) {
        approvalKeys.forEach((key) => settledApprovalKeys.add(key))
        continue
      }
      if (event.kind !== 'message_update') {
        continue
      }
      const message = event as any
      const approvalToken = message.toolCall?.approvalToken ?? null
      if (message.type !== 'ask' || !approvalToken || !child.runtimeId) {
        continue
      }
      if (approvalKeys.some((key) => settledApprovalKeys.has(key))) {
        continue
      }
      approvals.push({
        orchestrationId: snapshot.orchestrationId,
        runtimeId: child.runtimeId,
        assetId: child.assetId,
        assetName: child.assetName,
        command: message.toolCall?.command ?? message.toolCall?.displayText ?? '',
        approvalToken,
      })
    }
  }
  return approvals
}

export function useOrchestrationRun() {
  const [snapshot, setSnapshot] = useState<OrchestrationSnapshot | null>(null)
  const [targetPreview, setTargetPreview] = useState<OrchestrationTargetPreview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [resolvingTargets, setResolvingTargets] = useState(false)

  const pendingApprovals = useMemo(() => derivePendingApprovals(snapshot), [snapshot])

  const resolveTargets = useCallback(async (input: {
    prompt: string
    currentAsset: Asset | null
    assets: Asset[]
    conversationId: string
    modelName?: string | null
    selectedSkillName?: string | null
    maxConcurrency?: number
  }) => {
    setError(null)
    setResolvingTargets(true)
    try {
      const resolved = await resolveOrchestrationTargets({
        prompt: input.prompt,
        currentAssetId: input.currentAsset?.id ?? null,
        conversationId: input.conversationId,
        modelName: input.modelName ?? null,
      })
      setTargetPreview({
        ...resolved,
        prompt: input.prompt,
        assets: input.assets.filter((asset) => resolved.preparations.some((item) => item.assetId === asset.id)),
        currentAsset: input.currentAsset,
        conversationId: input.conversationId,
        modelName: input.modelName ?? null,
        selectedSkillName: input.selectedSkillName ?? null,
        maxConcurrency: input.maxConcurrency ?? 3,
      })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to resolve target assets.')
    } finally {
      setResolvingTargets(false)
    }
  }, [])

  const confirmAndRun = useCallback(async (targetAssetIds?: number[]) => {
    if (!targetPreview) {
      return
    }
    setError(null)
    setRunning(true)
    try {
      const stream = await streamRunOrchestration({
        prompt: targetPreview.prompt,
        currentAssetId: targetPreview.currentAsset?.id ?? null,
        targetAssetIds: targetAssetIds ?? targetPreview.targetAssetIds,
        confirmationToken: targetPreview.confirmationToken,
        conversationId: targetPreview.conversationId,
        modelName: targetPreview.modelName ?? null,
        selectedSkillName: targetPreview.selectedSkillName ?? null,
        maxConcurrency: targetPreview.maxConcurrency,
      })
      setTargetPreview(null)
      for await (const event of stream) {
        setSnapshot((current) => applyEvent(current, event))
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to run orchestration.')
    } finally {
      setRunning(false)
    }
  }, [targetPreview])

  const clearTargetPreview = useCallback(() => {
    setTargetPreview(null)
  }, [])

  const cancel = useCallback(async () => {
    if (!snapshot) {
      return
    }
    const event = await cancelOrchestration(snapshot.orchestrationId)
    setSnapshot((current) => applyEvent(current, event))
  }, [snapshot])

  const approveChildRun = useCallback(async (runtimeId: string, approvalToken: string | null, allowPrefix?: string) => {
    setError(null)
    try {
      if (!snapshot) {
        throw new Error('Orchestration snapshot is not available.')
      }
      const stream = await streamApproveOrchestrationChild(
        snapshot.orchestrationId,
        runtimeId,
        true,
        approvalToken ?? undefined,
        allowPrefix,
      )
      for await (const event of stream) {
        setSnapshot((current) => applyEvent(current, event))
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to approve child run.')
    }
  }, [snapshot])

  const rejectChildRun = useCallback(async (runtimeId: string, approvalToken: string | null) => {
    setError(null)
    try {
      if (!snapshot) {
        throw new Error('Orchestration snapshot is not available.')
      }
      const stream = await streamApproveOrchestrationChild(
        snapshot.orchestrationId,
        runtimeId,
        false,
        approvalToken ?? undefined,
      )
      for await (const event of stream) {
        setSnapshot((current) => applyEvent(current, event))
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to reject child run.')
    }
  }, [snapshot])

  const restoreFromConversation = useCallback(async (conversationId: string | null, events: EventItem[]) => {
    if (!conversationId) {
      setSnapshot(null)
      return
    }
    const orchestrationId = latestOrchestrationId(events, conversationId)
    if (!orchestrationId) {
      setSnapshot(null)
      return
    }
    const conversationSnapshot = replayConversationOrchestration(events, orchestrationId)
    if (hasReplayableProgress(conversationSnapshot) && isTerminalOrchestrationStatus(conversationSnapshot.status)) {
      setSnapshot(conversationSnapshot)
      return
    }
    try {
      const restoredSnapshot = await getOrchestrationSnapshot(orchestrationId)
      const restoredEvents = await getOrchestrationEvents(orchestrationId, 0)
      const replayedSnapshot = restoredEvents.events.reduce(
        (currentSnapshot, event) => applyEvent(currentSnapshot, event),
        restoredSnapshot as OrchestrationSnapshot | null,
      )
      setSnapshot(replayedSnapshot ?? conversationSnapshot)
    } catch {
      setSnapshot(conversationSnapshot)
    }
  }, [])

  return {
    snapshot,
    targetPreview,
    resolvingTargets,
    running,
    error,
    pendingApprovals,
    resolveTargets,
    confirmAndRun,
    clearTargetPreview,
    approveChildRun,
    rejectChildRun,
    restoreFromConversation,
    cancel,
  }
}
