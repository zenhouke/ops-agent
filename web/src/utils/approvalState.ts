import type { EventItem } from '../types/ops'

export function commandRuntimeCommandKey(runtimeId: unknown, command: unknown): string | null {
  const commandText = typeof command === 'string' ? command : ''
  if (!commandText) {
    return null
  }
  return `${typeof runtimeId === 'string' && runtimeId ? runtimeId : 'runtime'}:${commandText}`
}

function addApprovalKey(keys: string[], key: string | null | undefined): void {
  if (key && !keys.includes(key)) {
    keys.push(key)
  }
}

export function getApprovalKeys(event: EventItem): string[] {
  const keys: string[] = []
  if (event.kind === 'approval_required' || event.kind === 'approval_decision' || event.kind === 'approval_granted' || event.kind === 'approval_rejected') {
    addApprovalKey(keys, event.stepId)
    addApprovalKey(keys, commandRuntimeCommandKey(event.runtimeId, event.command))
    return keys
  }

  if (event.kind === 'command_start' || event.kind === 'execution_started') {
    addApprovalKey(keys, (event as any).stepId || (event as any).step_id)
    addApprovalKey(keys, commandRuntimeCommandKey((event as any).runtimeId, (event as any).command))
    return keys
  }

  if (event.kind === 'command_end' || event.kind === 'execution_completed') {
    addApprovalKey(keys, (event as any).stepId || (event as any).step_id)
    return keys
  }

  if ('type' in event && (event.type === 'ask' || (event.type === 'say' && event.say === 'tool_use'))) {
    const runtimeId = (event as any).runtimeId
    const command = event.toolCall?.command || event.toolCall?.args?.command || (event.toolCall?.args ? JSON.stringify(event.toolCall.args) : event.text || '')
    addApprovalKey(keys, commandRuntimeCommandKey(runtimeId, command))
    addApprovalKey(keys, event.toolCall?.id)
    addApprovalKey(keys, event.id)
  }
  return keys
}

export function isApprovalSettlingEvent(event: EventItem): boolean {
  return event.kind === 'approval_decision'
    || event.kind === 'approval_granted'
    || event.kind === 'approval_rejected'
    || event.kind === 'command_start'
    || event.kind === 'command_end'
    || event.kind === 'execution_started'
    || event.kind === 'execution_completed'
    || ('type' in event && event.type === 'say' && event.say === 'tool_use')
}
