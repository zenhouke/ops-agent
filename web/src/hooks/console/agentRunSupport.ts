import type { RefObject } from 'react'
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
  activeConversationAssetId: number | null
  activeConversationIdRef: RefObject<string | null>
  events: EventItem[]
  runtimeSummaries: RuntimeSummary[]
  setEvents: (updater: EventItem[] | ((previous: EventItem[]) => EventItem[])) => void
  createConversation: (assetId?: number | null) => Promise<string>
  upsertConversationSummary: (summary: ConversationSummary) => void
  refreshConversationList: () => Promise<unknown>
  syncConversationRuntimes: (conversationId: string) => Promise<RuntimeSummary[]>
  selectedAsset: Asset
  activeTerminalTab: { sessionId: string | null } | null
  selectedModel: string
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
  if (/failed to fetch|networkerror|load failed/i.test(message)) {
    return '无法连接到 Ops Agent 后端。请确认服务已启动，恢复连接后可直接重试。'
  }
  if (/model is not found|model_not_found/i.test(message)) {
    return '模型供应商未找到当前模型。请在模型设置中重新发现模型后重试。'
  }
  if (/concurrency limit|too many concurrent/i.test(message)) {
    return '模型供应商并发额度已满。请等待当前请求结束后重试，或检查供应商账户的并发限制。'
  }
  if (/only allows clients matched by the configured tls router/i.test(message)) {
    return '当前 API Key 限制了客户端类型，不能用于 Ops Agent。请调整供应商 TLS Router 限制或更换 Key。'
  }
  if (/request timed out|\btimeout\b|timed out/i.test(message)) {
    return '模型供应商响应超时。请检查连接或增加模型超时时间后重试。'
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

export function derivePendingApprovalState(events: EventItem[], terminalRuntimeIds: ReadonlySet<string> = new Set()): PendingApprovalState | null {
  const settled = new Set<string>()
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index]
    const runtimeId = 'runtimeId' in event && typeof event.runtimeId === 'string' ? event.runtimeId : null
    if (runtimeId && terminalRuntimeIds.has(runtimeId)) continue
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
