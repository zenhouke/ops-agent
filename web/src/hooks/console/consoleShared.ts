import type { AgentMessage, Asset, ConversationSummary, EventItem, PlanStepStatus } from '../../types/ops'

export const LOCAL_TERMINAL_ASSET_ID = 0
export const PENDING_ASSISTANT_MESSAGE_ID = '__pending_assistant__'

const terminalAutonomyKinds = new Set([
  'terminal_session_request',
  'terminal_session_opened',
  'terminal_session_rejected',
  'terminal_authorization_revoked',
  'terminal_command_submitted',
])

export function isTerminalAutonomyEvent(event: { kind?: string }): boolean {
  return Boolean(event.kind && terminalAutonomyKinds.has(event.kind))
}

function getEventId(event: EventItem): string | undefined {
  return 'eventId' in event && typeof event.eventId === 'string' ? event.eventId : undefined
}

function getTerminalRequestId(event: EventItem): string | undefined {
  return event.kind === 'terminal_session_request' && typeof event.requestId === 'string' ? event.requestId : undefined
}

function isSameTerminalAutonomyEvent(left: EventItem, right: EventItem): boolean {
  const leftRequestId = getTerminalRequestId(left)
  const rightRequestId = getTerminalRequestId(right)
  if (leftRequestId && rightRequestId) {
    return left.kind === right.kind && leftRequestId === rightRequestId
  }

  const leftEventId = getEventId(left)
  const rightEventId = getEventId(right)
  return Boolean(
    (leftEventId && (right.id === leftEventId || rightEventId === leftEventId))
    || (rightEventId && left.id === rightEventId)
    || left.id === right.id
  )
}

function getApprovalToken(event: EventItem): string | null | undefined {
  if ('toolCall' in event) return event.toolCall?.approvalToken
  if (event.kind === 'terminal_session_request') return event.approvalToken
  return undefined
}

function getEventSequence(event: EventItem): number | undefined {
  return 'sequence' in event && typeof event.sequence === 'number' ? event.sequence : undefined
}

export function mergeEventsBySequence(events: EventItem[]): EventItem[] {
  return events
    .map((event, index) => ({ event, index }))
    .sort((left, right) => {
      const leftSequence = getEventSequence(left.event)
      const rightSequence = getEventSequence(right.event)
      if (leftSequence !== undefined && rightSequence !== undefined && leftSequence !== rightSequence) {
        return leftSequence - rightSequence
      }
      return left.index - right.index
    })
    .map(({ event }) => event)
}

export const defaultLocalTerminalAsset: Asset = {
  id: LOCAL_TERMINAL_ASSET_ID,
  groupId: null,
  name: 'localhost',
  assetType: 'local_terminal',
  host: '',
  port: 0,
  username: '',
  authType: '',
  tags: [],
  vendor: '',
  description: 'Default local terminal',
  sshKeyId: null,
  proxyAssetId: null,
}

export function normalizePlanEvents(rawEvents: EventItem[]): EventItem[] {
  const latestPlanEventIndexByPlanId = new Map<string, number>()

  rawEvents.forEach((event, index) => {
    if (event.kind !== 'plan') {
      return
    }

    const planId = event.planId ?? event.id
    latestPlanEventIndexByPlanId.set(planId, index)
  })

  return rawEvents.map((event, index) => {
    if (event.kind !== 'plan') {
      return event
    }

    const normalizedSteps = event.steps.map((step, stepIndex, steps) => {
      if (step.status) {
        return step
      }

      const fallbackStatus: PlanStepStatus = stepIndex === steps.length - 1 ? 'running' : 'completed'
      return {
        ...step,
        status: fallbackStatus,
      }
    })

    const planId = event.planId ?? event.id
    const latestIndex = latestPlanEventIndexByPlanId.get(planId) ?? index
    return {
      ...event,
      planId,
      title: event.title ?? 'Task Plan',
      loading: event.loading ?? false,
      version: event.version ?? latestIndex + 1,
      isLatest: index === latestIndex,
      updated: event.updated ?? index !== latestIndex,
      steps: normalizedSteps,
    }
  })
}

export function buildTerminalWebSocketUrl(terminalSessionId: string, runtimeApiBaseUrl?: string | null): string {
  const apiBaseUrl = runtimeApiBaseUrl ?? import.meta.env.VITE_API_BASE_URL

  if (apiBaseUrl && apiBaseUrl.length > 0) {
    const baseUrl = new URL(apiBaseUrl, window.location.origin)
    baseUrl.protocol = baseUrl.protocol === 'https:' ? 'wss:' : 'ws:'
    baseUrl.pathname = `/api/terminal/sessions/${terminalSessionId}/ws`
    baseUrl.search = ''
    baseUrl.hash = ''
    return baseUrl.toString()
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/api/terminal/sessions/${terminalSessionId}/ws`
}

export function upsertConversationSummary(
  currentItems: ConversationSummary[],
  summary: ConversationSummary
): ConversationSummary[] {
  const nextItems = currentItems.filter((item) => item.id !== summary.id)
  return [summary, ...nextItems]
}

/**
 * 合并 delta 事件到现有事件列表
 */
export function mergeDeltaEvent(
  currentEvents: EventItem[],
  messageId: string,
  deltaText: string,
  stage?: string
): EventItem[] {
  const filteredEvents = currentEvents.filter((event) => event.id !== PENDING_ASSISTANT_MESSAGE_ID)
  const existingIndex = filteredEvents.findIndex((e) => e.id === messageId)
  
  const mergedEvent: EventItem = {
    id: messageId,
    kind: 'delta',
    messageId,
    text: deltaText,
    stage,
  }

  if (existingIndex >= 0) {
    const updated = [...filteredEvents]
    updated[existingIndex] = mergedEvent
    return normalizePlanEvents(updated)
  }
  
  return normalizePlanEvents([...filteredEvents, mergedEvent])
}

/**
 * 将 delta 缓冲区转换为最终事件列表
 */
export function flushDeltaBuffer(
  deltaBuffer: Map<string, string>,
  existingEvents: EventItem[]
): EventItem[] {
  const finalEvents: EventItem[] = []
  
  for (const [messageId, text] of deltaBuffer.entries()) {
    const existingEvent = existingEvents.find((e) => e.id === messageId)
    const finalEvent: EventItem = {
      id: messageId,
      kind: 'delta',
      messageId,
      text,
      stage: existingEvent && 'stage' in existingEvent ? existingEvent.stage : undefined,
    }
    finalEvents.push(finalEvent)
  }
  
  return finalEvents
}

export function upsertStreamEvent(
  currentEvents: EventItem[],
  event: EventItem
): EventItem[] {
  if (event.kind === 'error') {
    const settledEvents = currentEvents
      .filter((currentEvent) => currentEvent.id !== PENDING_ASSISTANT_MESSAGE_ID)
      .map((currentEvent) => currentEvent.kind === 'message' && currentEvent.partial
        ? { ...currentEvent, partial: false }
        : currentEvent)
    let lastUserIndex = -1
    settledEvents.forEach((currentEvent, index) => {
      if (currentEvent.kind === 'user') lastUserIndex = index
    })
    const alreadyShownForCurrentTurn = settledEvents
      .slice(lastUserIndex + 1)
      .some((currentEvent) => currentEvent.kind === 'error' && currentEvent.text === event.text)

    return normalizePlanEvents(alreadyShownForCurrentTurn ? settledEvents : [...settledEvents, event])
  }

  if (isTerminalAutonomyEvent(event)) {
    const nextEvents = currentEvents.map((currentEvent) => {
      if (isSameTerminalAutonomyEvent(currentEvent, event)) {
        return event
      }
      return currentEvent
    })
    const hasExistingEvent = currentEvents.some((currentEvent) => isSameTerminalAutonomyEvent(currentEvent, event))
    return normalizePlanEvents(hasExistingEvent ? nextEvents : [...currentEvents, event])
  }

  if (event.kind !== 'plan') {
    return normalizePlanEvents([...currentEvents, event])
  }

  const incomingPlanId = event.planId ?? event.id
  const nextEvents = currentEvents.map((currentEvent) => {
    if (currentEvent.kind !== 'plan') {
      return currentEvent
    }

    const currentPlanId = currentEvent.planId ?? currentEvent.id
    return currentPlanId === incomingPlanId ? event : currentEvent
  })

  const hasExistingPlan = currentEvents.some((currentEvent) => {
    if (currentEvent.kind !== 'plan') {
      return false
    }
    const currentPlanId = currentEvent.planId ?? currentEvent.id
    return currentPlanId === incomingPlanId
  })

  return normalizePlanEvents(hasExistingPlan ? nextEvents : [...currentEvents, event])
}

/**
 * 更新或插入 AgentMessage 到事件列表
 */
export function upsertMessageEvent(
  currentEvents: EventItem[],
  message: AgentMessage
): EventItem[] {
  const existingIndex = currentEvents.findIndex((e) => e.id === message.id)
  if (existingIndex !== -1) {
    const newEvents = [...currentEvents]
    newEvents[existingIndex] = message
    return normalizePlanEvents(newEvents)
  }
  
  // If not found, filter out deltas and append
  const filteredEvents = currentEvents.filter((e) => e.kind !== 'delta' && e.id !== PENDING_ASSISTANT_MESSAGE_ID)
  return normalizePlanEvents([...filteredEvents, message])
}
