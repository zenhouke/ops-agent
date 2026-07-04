import type { EventItem, AgentMessage } from '../../../types/ops'
import type { CommandChunk, CommandEnd, DeltaEvent, Group } from './types'

export type ConversationTurn = {
  id: string
  userEvent?: EventItem
  assistantGroups: Group[]
}

export function collectSettledTerminalRequestIds(events: EventItem[]) {
  const settledTerminalRequestIds = new Set<string>()
  for (const event of events) {
    if ((event.kind === 'terminal_session_opened' || event.kind === 'terminal_session_rejected') && event.requestId) {
      settledTerminalRequestIds.add(event.requestId)
    }
  }
  return settledTerminalRequestIds
}

function commandRuntimeCommandKey(runtimeId: unknown, command: unknown): string | null {
  const commandText = typeof command === 'string' ? command : ''
  if (!commandText) return null
  return `${typeof runtimeId === 'string' && runtimeId ? runtimeId : 'runtime'}:${commandText}`
}

function commandApprovalAliasKeys(event: EventItem): string[] {
  const keys: string[] = []
  const addKey = (key: string | null | undefined) => {
    if (key && !keys.includes(key)) keys.push(key)
  }

  if (event.kind === 'approval_required' || event.kind === 'approval_decision' || event.kind === 'approval_granted' || event.kind === 'approval_rejected') {
    addKey(commandRuntimeCommandKey(event.runtimeId, event.command))
    addKey(event.stepId)
    return keys
  }

  if (event.kind === 'command_start' || event.kind === 'execution_started') {
    addKey(commandRuntimeCommandKey((event as any).runtimeId, (event as any).command))
    addKey((event as any).stepId || (event as any).step_id)
    return keys
  }

  if ('type' in event && (event.type === 'ask' || (event.type === 'say' && event.say === 'tool_use')) && event.toolCall) {
    const runtimeId = (event as any).runtimeId || event.toolCall.args?.runtime_id || 'runtime'
    const command = event.toolCall.command || event.toolCall.args?.command || (event.toolCall.args ? JSON.stringify(event.toolCall.args) : event.text || '')
    addKey(commandRuntimeCommandKey(runtimeId, command))
    return keys
  }

  return keys
}

function commandApprovalKey(event: EventItem): string | null {
  return commandApprovalAliasKeys(event)[0] ?? null
}

function mergeToolCallMessage(current: AgentMessage | undefined, incoming: AgentMessage): AgentMessage {
  if (!current) return incoming
  return {
    ...current,
    ...incoming,
    text: incoming.text || current.text,
    toolOutput: incoming.toolOutput ?? current.toolOutput,
    exitCode: incoming.exitCode ?? current.exitCode,
    toolCall: {
      ...(current.toolCall ?? {}),
      ...(incoming.toolCall ?? {}),
      args: {
        ...(current.toolCall?.args ?? {}),
        ...(incoming.toolCall?.args ?? {}),
      },
      approvalToken: incoming.toolCall?.approvalToken ?? current.toolCall?.approvalToken ?? null,
    } as AgentMessage['toolCall'],
  }
}

export function buildConversationGroups(events: EventItem[]): Group[] {
  const groups: Group[] = []
  const shouldSuppressEmptyPartial = (eventIndex: number, event: EventItem): boolean => {
    if (
      !('type' in event)
      || event.type !== 'say'
      || event.say !== 'text'
      || !event.partial
      || event.text
      || event.thinking
      || event.toolCall
    ) {
      return false
    }

    for (let index = eventIndex - 1; index >= 0; index--) {
      const candidate = events[index]
      if (candidate.kind === 'user') break
      if (candidate.kind === 'error' || candidate.kind === 'failed' || candidate.kind === 'completed' || candidate.kind === 'final' || (candidate.kind === 'plan' && candidate.status === 'waiting_plan_approval')) {
        return true
      }
    }
    for (let index = eventIndex + 1; index < events.length; index++) {
      const candidate = events[index]
      if (candidate.kind === 'user') break
      if (candidate.kind === 'error' || candidate.kind === 'failed' || candidate.kind === 'completed' || candidate.kind === 'final' || (candidate.kind === 'plan' && candidate.status === 'waiting_plan_approval')) {
        return true
      }
    }
    return false
  }
  const commandGroupMap = new Map<string, { index: number }>()
  const approvalGroupMap = new Map<string, { index: number }>()
  const toolCallGroupMap = new Map<string, { index: number }>()
  const explicitApprovalKeys = new Set(events
    .filter((event) => event.kind === 'approval_required' || event.kind === 'approval_decision' || event.kind === 'approval_granted' || event.kind === 'approval_rejected')
    .flatMap(commandApprovalAliasKeys))
  let currentDeltaGroup: DeltaEvent[] = []
  let deltaGroupCounter = 0

  const flushDeltaGroup = () => {
    if (currentDeltaGroup.length === 0) return
    groups.push({ type: 'thinking', deltas: currentDeltaGroup, key: `chain-${deltaGroupCounter++}` })
    currentDeltaGroup = []
  }

  for (const [eventIndex, event] of events.entries()) {
    if (event.kind === 'terminal_status') continue

    if (event.kind === 'delta') {
      currentDeltaGroup.push(event)
      continue
    }

    flushDeltaGroup()

    if (event.kind === 'approval_required' || event.kind === 'approval_decision' || event.kind === 'approval_granted' || event.kind === 'approval_rejected') {
      const key = commandApprovalKey(event) ?? `${event.runtimeId || 'runtime'}:${event.command}`
      const aliasKeys = commandApprovalAliasKeys(event)
      const existing = aliasKeys.map((aliasKey) => approvalGroupMap.get(aliasKey)).find(Boolean)
      if (existing) {
        const target = groups[existing.index]
        if (target.type === 'command') {
          let updatedStatus = target.approvalEvent?.status
          if (event.kind === 'approval_granted') updatedStatus = 'approved'
          if (event.kind === 'approval_rejected') updatedStatus = 'rejected'
          if (event.status) updatedStatus = event.status

          target.approvalEvent = {
            ...(target.approvalEvent ?? event),
            ...event,
            status: updatedStatus,
            command: event.command || target.approvalEvent?.command || target.startEvent?.command || '',
          }
        }
      } else {
        let initStatus = event.status
        if (event.kind === 'approval_granted') initStatus = 'approved'
        if (event.kind === 'approval_rejected') initStatus = 'rejected'

        const commandGroup = {
          type: 'command' as const,
          key: `approval-${key}`,
          approvalEvent: { ...event, status: initStatus },
          chunkEvents: [] as CommandChunk[],
        }
        const insertIndex = groups.length
        groups.push(commandGroup)
        aliasKeys.forEach((aliasKey) => approvalGroupMap.set(aliasKey, { index: insertIndex }))
      }
      continue
    }

    if (event.kind === 'command_start' || event.kind === 'execution_started') {
      const commandId = (event as any).commandId || (event as any).command_id
      const aliasKeys = commandApprovalAliasKeys(event)
      const existingApproval = aliasKeys.map((aliasKey) => approvalGroupMap.get(aliasKey) ?? toolCallGroupMap.get(aliasKey)).find(Boolean)
      if (existingApproval) {
        const target = groups[existingApproval.index]
        if (target.type === 'command') {
          target.startEvent = { ...event, commandId } as any
          commandGroupMap.set(commandId, { index: existingApproval.index })
        }
      } else {
        const group = { type: 'command' as const, key: `cmd-${commandId}`, startEvent: { ...event, commandId } as any, chunkEvents: [] as CommandChunk[], endEvent: undefined as CommandEnd | undefined }
        const insertIndex = groups.length
        groups.push(group)
        commandGroupMap.set(commandId, { index: insertIndex })
      }
      continue
    }

    if (event.kind === 'command_chunk' || event.kind === 'execution_output') {
      const commandId = (event as any).commandId || (event as any).command_id
      const ref = commandGroupMap.get(commandId)
      if (ref) {
        const target = groups[ref.index]
        if (target.type === 'command') target.chunkEvents.push({ ...event, commandId } as any)
      }
      continue
    }

    if (event.kind === 'command_end' || event.kind === 'execution_completed') {
      const commandId = (event as any).commandId || (event as any).command_id
      const ref = commandGroupMap.get(commandId)
      if (ref) {
        const target = groups[ref.index]
        if (target.type === 'command') target.endEvent = { ...event, commandId, exitCode: (event as any).exitCode ?? (event as any).exit_code } as any
      }
      continue
    }

    if ('type' in event && (event.type === 'say' || event.type === 'ask')) {
      if (shouldSuppressEmptyPartial(eventIndex, event)) {
        continue
      }
      if (event.toolCall) {
        const aliasKeys = commandApprovalAliasKeys(event)
        const key = aliasKeys[0] ?? null
        const existing = aliasKeys
          .map((aliasKey) => approvalGroupMap.get(aliasKey) ?? toolCallGroupMap.get(aliasKey))
          .find(Boolean)
        if (existing) {
          const target = groups[existing.index]
          if (target.type === 'command') {
            target.message = mergeToolCallMessage(target.message, event as AgentMessage)
          }
          continue
        }
        if (key) {
          const group = { type: 'command' as const, key: `tool-${key}`, message: event as AgentMessage, chunkEvents: [] as CommandChunk[], endEvent: undefined as CommandEnd | undefined }
          const insertIndex = groups.length
          groups.push(group)
          aliasKeys.forEach((aliasKey) => toolCallGroupMap.set(aliasKey, { index: insertIndex }))
          continue
        }
      }
      groups.push({ type: 'thinking', message: event as AgentMessage, key: `msg-${event.id}` })
      continue
    }

    groups.push({ type: 'event', event })
  }

  flushDeltaGroup()
  return groups
}

export function buildConversationTurns(groups: Group[]): ConversationTurn[] {
  const turns: ConversationTurn[] = []
  let currentTurn: ConversationTurn = { id: 'turn-0', assistantGroups: [] }
  let turnCounter = 0

  groups.forEach((entry) => {
    if (entry.type === 'event' && entry.event.kind === 'user') {
      if (currentTurn.userEvent || currentTurn.assistantGroups.length > 0) {
        turns.push(currentTurn)
        turnCounter++
      }
      currentTurn = { id: `turn-${turnCounter}`, userEvent: entry.event, assistantGroups: [] }
    } else {
      currentTurn.assistantGroups.push(entry)
    }
  })

  if (currentTurn.userEvent || currentTurn.assistantGroups.length > 0) {
    turns.push(currentTurn)
  }

  return turns
}
