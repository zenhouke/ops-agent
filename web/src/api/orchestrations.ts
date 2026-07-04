import { requestEventStream, requestJson } from './client'
import type {
  ConsoleOrchestrationResolveTargetsRequest,
  ConsoleOrchestrationResolveTargetsResponseDto,
  ConsoleOrchestrationRunRequest,
  OrchestrationEventsResponseDto,
  OrchestrationSnapshotDto,
} from '../types/api'
import type { EventItem, OrchestrationChildStatus, OrchestrationSnapshot, OrchestrationTargetPreparation } from '../types/ops'

export type ResolvedOrchestrationTargets = {
  targetAssetIds: number[]
  targetSelectionSource: string
  targetSelectionReason: string
  confidence: 'high' | 'medium' | 'low'
  confirmationToken: string
  preparations: OrchestrationTargetPreparation[]
}

function parseSseBlock(block: string): EventItem | null {
  const lines = block.split('\n')
  const dataLines = lines.filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trim())
  if (dataLines.length === 0) {
    return null
  }
  return JSON.parse(dataLines.join('\n')) as EventItem
}

async function* readEventStream(response: Response): AsyncGenerator<EventItem, void, void> {
  const reader = response.body?.getReader()
  if (!reader) {
    return
  }
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      break
    }
    buffer += decoder.decode(value, { stream: true })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() ?? ''
    for (const block of blocks) {
      const event = parseSseBlock(block)
      if (event) {
        yield event
      }
    }
  }
  if (buffer.trim()) {
    const event = parseSseBlock(buffer)
    if (event) {
      yield event
    }
  }
}

function mapSnapshot(dto: OrchestrationSnapshotDto): OrchestrationSnapshot {
  return {
    orchestrationId: dto.orchestrationId,
    conversationId: dto.conversationId,
    prompt: dto.prompt,
    targetAssetIds: dto.targetAssetIds,
    targetSelectionSource: dto.targetSelectionSource,
    targetSelectionReason: dto.targetSelectionReason,
    confidence: dto.confidence,
    status: dto.status as OrchestrationSnapshot['status'],
    maxConcurrency: dto.maxConcurrency,
    children: dto.children.map((child) => ({
      assetId: child.assetId,
      assetName: child.assetName,
      runtimeId: child.runtimeId,
      terminalId: child.terminalId,
      status: child.status as OrchestrationChildStatus,
      summary: child.summary,
      errorMessage: child.errorMessage,
      lastSequence: child.lastSequence,
      events: [],
    })),
    finalSummary: dto.finalSummary,
    createdAt: dto.createdAt,
    updatedAt: dto.updatedAt,
    lastSequence: dto.lastSequence,
  }
}

export async function resolveOrchestrationTargets(input: ConsoleOrchestrationResolveTargetsRequest): Promise<ResolvedOrchestrationTargets> {
  const response = await requestJson<ConsoleOrchestrationResolveTargetsResponseDto>('/api/console/orchestrations/resolve-targets', {
    method: 'POST',
    body: JSON.stringify(input),
  })
  return {
    targetAssetIds: response.targetAssetIds,
    targetSelectionSource: response.targetSelectionSource,
    targetSelectionReason: response.targetSelectionReason,
    confidence: response.confidence,
    confirmationToken: response.confirmationToken,
    preparations: response.preparations.map((item) => ({
      assetId: item.assetId,
      assetName: item.assetName,
      status: item.status,
      terminalId: item.terminalId,
      reason: item.reason,
    })),
  }
}

export async function streamRunOrchestration(input: ConsoleOrchestrationRunRequest): Promise<AsyncGenerator<EventItem, void, void>> {
  const response = await requestEventStream('/api/console/orchestrations/run', {
    method: 'POST',
    body: JSON.stringify(input),
  })
  return readEventStream(response)
}

export async function getOrchestrationSnapshot(orchestrationId: string): Promise<OrchestrationSnapshot> {
  return mapSnapshot(await requestJson<OrchestrationSnapshotDto>(`/api/console/orchestrations/${orchestrationId}/snapshot`))
}

export async function getOrchestrationEvents(orchestrationId: string, since = 0): Promise<{ latestSequence: number; events: EventItem[] }> {
  const response = await requestJson<OrchestrationEventsResponseDto>(`/api/console/orchestrations/${orchestrationId}/events?since=${since}`)
  return {
    latestSequence: response.latestSequence,
    events: response.events as EventItem[],
  }
}

export async function cancelOrchestration(orchestrationId: string): Promise<EventItem> {
  return requestJson<EventItem>(`/api/console/orchestrations/${orchestrationId}/cancel`, { method: 'POST' })
}

export async function streamApproveOrchestrationChild(
  orchestrationId: string,
  runtimeId: string,
  approved: boolean,
  approvalToken?: string,
  allowPrefix?: string,
): Promise<AsyncGenerator<EventItem, void, void>> {
  const response = await requestEventStream(`/api/console/orchestrations/${orchestrationId}/approval`, {
    method: 'POST',
    body: JSON.stringify({
      runtimeId,
      approved,
      approvalToken: approvalToken ?? null,
      allowPrefix: allowPrefix?.trim() || null,
    }),
  })
  return readEventStream(response)
}
