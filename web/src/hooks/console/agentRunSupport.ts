import type { RefObject } from 'react'
import type { RunMode } from '../../types/api'
import type {
  AgentMessage,
  Asset,
  ConversationContextStatus,
  ConversationSummary,
  EventItem,
  RuntimeSummary,
} from '../../types/ops'
import { mergeDeltaEvent } from './consoleShared'

export interface UseAgentRunProps {
  activeConversationId: string | null
  activeConversationTitle: string
  activeConversationIdRef: RefObject<string | null>
  events: EventItem[]
  setEvents: (updater: EventItem[] | ((previous: EventItem[]) => EventItem[])) => void
  createConversation: () => Promise<string>
  upsertConversationSummary: (summary: ConversationSummary) => void
  refreshConversationList: () => Promise<unknown>
  syncConversationRuntimes: (conversationId: string) => Promise<RuntimeSummary[]>
  selectedAsset: Asset
  activeTerminalTab: { sessionId: string | null } | null
  selectedModel: string
  runMode: RunMode
  setLoadError: (error: string | null) => void
  setContextStatus: (
    status:
      | ConversationContextStatus
      | null
      | ((current: ConversationContextStatus | null) => ConversationContextStatus)
  ) => void
}

export type BackgroundRunStatus = 'running' | 'needs_approval' | 'completed' | 'failed'

export type BackgroundRunState = {
  conversationId: string
  title: string
  status: BackgroundRunStatus
  hasUnread: boolean
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
    || error instanceof Error && error.message.toLowerCase().includes('signal is aborted')
}

export function getRunErrorMessage(error: unknown): string {
  const message = error instanceof Error ? error.message : 'Failed to run agent.'
  if (/quota_exceeded_error|\b429\b.*\b(exhausted|quota)\b/i.test(message)) {
    return '模型供应商额度已用尽（HTTP 429）。请更换模型或检查供应商账户额度后重试。'
  }
  return message
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

export function createDeltaBatcher({
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
    setEvents((currentEvents) =>
      items.reduce(
        (nextEvents, item) => mergeDeltaEvent(nextEvents, item.messageId, item.text, item.stage),
        currentEvents,
      ),
    )
  }

  return {
    push(item: DeltaBatchItem) {
      pending.set(item.messageId, item)
      if (timer === null) {
        timer = window.setTimeout(flush, DELTA_FLUSH_INTERVAL_MS)
      }
    },
    cancel() {
      if (timer !== null) {
        window.clearTimeout(timer)
        timer = null
      }
      pending.clear()
    },
    flush,
  }
}

function getApprovalKey(event: EventItem) {
  if (
    event.kind === 'approval_required'
    || event.kind === 'approval_decision'
    || event.kind === 'approval_granted'
    || event.kind === 'approval_rejected'
  ) {
    return event.stepId || `${event.runtimeId || 'runtime'}:${event.command}`
  }
  if ('type' in event && (event.type === 'ask' || (event.type === 'say' && event.say === 'tool_use'))) {
    const runtimeId = (event as AgentMessage & { runtimeId?: string }).runtimeId
    const command = event.toolCall?.command
      || (event.toolCall?.args ? JSON.stringify(event.toolCall.args) : event.text || '')
    return `${runtimeId || 'runtime'}:${command}`
  }
  return null
}

export function derivePendingApprovalState(events: EventItem[]): PendingApprovalState | null {
  const settled = new Set<string>()
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index]
    const approvalKey = getApprovalKey(event)
    const isSettled = event.kind === 'approval_decision'
      || event.kind === 'approval_granted'
      || event.kind === 'approval_rejected'
      || ('type' in event && event.type === 'say' && event.say === 'tool_use')
    if (approvalKey && isSettled) {
      settled.add(approvalKey)
      continue
    }
    if (!approvalKey || settled.has(approvalKey)) {
      continue
    }
    if (event.kind === 'approval_required' && event.status !== 'approved' && event.status !== 'rejected' && event.runtimeId) {
      return { runtimeId: event.runtimeId, approvalToken: event.approvalToken ?? null, approvalKey }
    }
    if ('type' in event && event.type === 'ask') {
      const runtimeId = (event as AgentMessage & { runtimeId?: string }).runtimeId
      if (runtimeId) {
        return { runtimeId, approvalToken: event.toolCall?.approvalToken ?? null, approvalKey }
      }
    }
  }
  return null
}
