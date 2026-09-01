import { mapAsset } from './assets'
import { requestEventStream, requestJson } from './client'
import { mapAssetGroup, type AssetGroupDto } from './groups'
import type {
  ConsoleBootstrap,
  ConsoleRunRequest,
  ConsoleRunRequestDto,
  RuntimeEventsResponseDto,
  RuntimeSnapshotDto,
  RuntimeSummaryDto,
} from '../types/api'
import type { EventItem, RuntimeEventEnvelope, RuntimeSnapshot, RuntimeSummary } from '../types/ops'

type ConsoleBootstrapDto = Omit<ConsoleBootstrap, 'assets' | 'groups'> & {
  assets: Parameters<typeof mapAsset>[0][]
  groups: AssetGroupDto[]
}

export async function getConsoleBootstrap(): Promise<ConsoleBootstrap> {
  const bootstrap = await requestJson<ConsoleBootstrapDto>('/api/console/bootstrap')
  return {
    ...bootstrap,
    assets: bootstrap.assets.map(mapAsset),
    groups: bootstrap.groups.map(mapAssetGroup),
  }
}

function mapRuntimeSummary(dto: RuntimeSummaryDto): RuntimeSummary {
  return {
    runtimeId: dto.runtime_id,
    conversationId: dto.conversation_id,
    assetId: dto.asset_id,
    terminalId: dto.terminal_id,
    status: dto.status,
    runState: dto.run_state,
    loadedSkillName: dto.loaded_skill_name,
    currentStepId: dto.current_step_id,
    pendingApprovalStepId: dto.pending_approval_step_id,
    updatedAt: dto.updated_at,
  }
}

function mapRuntimeSnapshot(dto: RuntimeSnapshotDto): RuntimeSnapshot {
  return {
    runtimeId: dto.runtime_id,
    conversationId: dto.conversation_id,
    assetId: dto.asset_id,
    conversationScopeMode: dto.conversation_scope_mode,
    conversationPrimaryAssetId: dto.conversation_primary_asset_id,
    allowedAssetIds: dto.allowed_asset_ids,
    terminalId: dto.terminal_id,
    status: dto.status,
    runState: dto.run_state,
    loadedSkillName: dto.loaded_skill_name,
    taskState: dto.task_state,
    steps: dto.steps.map((step) => ({
      stepId: step.step_id,
      title: step.title,
      command: step.command,
      reason: step.reason,
      riskLevel: step.risk_level,
      workingDirectory: step.working_directory,
      expectedOutput: step.expected_output,
      status: step.status,
      output: step.output,
      exitCode: step.exit_code,
    })),
    currentStepId: dto.current_step_id,
    pendingApprovalStepId: dto.pending_approval_step_id,
    pendingApprovalToken: dto.pending_approval_token ?? null,
    pendingFollowupQuestion: dto.pending_followup_question ?? null,
    pendingUserMessageCount: dto.pending_user_message_count ?? 0,
    lastOutputExcerpt: dto.last_output_excerpt,
    summary: dto.summary,
    errorMessage: dto.error_message,
    recoveryAction: dto.recovery_action ?? null,
    recoveryCheckpoint: dto.recovery_checkpoint ?? null,
    terminalRequests: (dto.terminalRequests ?? []).map((request) => ({
      requestId: request.requestId,
      runtimeId: request.runtimeId,
      assetId: request.assetId,
      assetName: request.assetName,
      reason: request.reason,
      userDecisionStatus: request.userDecisionStatus,
      terminalCreationStatus: request.terminalCreationStatus,
      expiresAt: request.expiresAt,
      approvalToken: request.approvalToken ?? null,
      failureReason: request.failureReason ?? null,
      scopeExpansionRequired: request.scopeExpansionRequired ?? false,
    })),
    terminalAuthorizations: (dto.terminalAuthorizations ?? []).map((authorization) => ({
      authorizationId: authorization.authorizationId,
      runtimeId: authorization.runtimeId,
      assetId: authorization.assetId,
      assetName: authorization.assetName,
      terminalId: authorization.terminalId,
      source: authorization.source,
      approvedBy: authorization.approvedBy,
      requestId: authorization.requestId ?? null,
      status: authorization.status,
      replacedByAuthorizationId: authorization.replacedByAuthorizationId ?? null,
      revokeReason: authorization.revokeReason ?? null,
    })),
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
    lastSequence: dto.last_sequence,
  }
}

export async function listConversationRuntimes(conversationId: string): Promise<RuntimeSummary[]> {
  const runtimes = await requestJson<RuntimeSummaryDto[]>(`/api/console/conversations/${conversationId}/runtimes`)
  return runtimes.map(mapRuntimeSummary)
}

export async function getRuntimeSnapshot(runtimeId: string): Promise<RuntimeSnapshot> {
  const snapshot = await requestJson<RuntimeSnapshotDto>(`/api/console/runtimes/${runtimeId}/snapshot`)
  return mapRuntimeSnapshot(snapshot)
}

export async function getRuntimeEvents(runtimeId: string, since = 0): Promise<{ latestSequence: number; events: RuntimeEventEnvelope[] }> {
  const response = await requestJson<RuntimeEventsResponseDto>(`/api/console/runtimes/${runtimeId}/events?since=${since}`)
  return {
    latestSequence: response.latest_sequence,
    events: response.events as RuntimeEventEnvelope[],
  }
}

export async function streamReconnectRuntime(
  runtimeId: string,
  since: number,
  signal?: AbortSignal,
): Promise<AsyncGenerator<EventItem, void, void>> {
  const response = await requestEventStream(`/api/console/runtimes/${runtimeId}/reconnect?since=${since}`, {
    method: 'POST',
    signal,
  })
  return readEventStream(response)
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

function buildConsoleRunRequestDto({
  prompt,
  mode,
  assetId,
  terminalId,
  modelName,
  conversationId,
  userEventId,
  selectedSkillName,
}: ConsoleRunRequest): ConsoleRunRequestDto {
  return {
    prompt,
    mode,
    asset_id: assetId,
    terminal_id: terminalId,
    model_name: modelName,
    conversation_id: conversationId,
    user_event_id: userEventId,
    ...(selectedSkillName != null ? { selected_skill_name: selectedSkillName } : {}),
  }
}

export async function streamRunAgent(
  prompt: string,
  assetId?: number,
  terminalId?: string | null,
  modelName?: string,
  conversationId?: string,
  userEventId?: string,
  selectedSkillName?: string | null,
  mode: 'standard' | 'incident' = 'standard',
  signal?: AbortSignal,
): Promise<AsyncGenerator<EventItem, void, void>> {
  const response = await requestEventStream('/api/console/run', {
    method: 'POST',
    signal,
    body: JSON.stringify(
      buildConsoleRunRequestDto({
        prompt,
        mode,
        assetId,
        terminalId,
        modelName,
        conversationId,
        userEventId,
        selectedSkillName,
      }),
    ),
  })
  return readEventStream(response)
}

export async function cancelAgentRuntime(runtimeId: string): Promise<void> {
  await requestJson(`/api/console/runtimes/${encodeURIComponent(runtimeId)}/cancel`, {
    method: 'POST',
  })
}

export async function streamRuntimeMessage(
  runtimeId: string,
  message: string,
): Promise<AsyncGenerator<EventItem, void, void>> {
  const response = await requestEventStream(`/api/console/runtimes/${encodeURIComponent(runtimeId)}/messages`, {
    method: 'POST',
    body: JSON.stringify({ message }),
  })
  return readEventStream(response)
}

export async function streamApproveAgent(runtimeId: string, approved: boolean, approvalToken?: string, allowPrefix?: string, guidance?: string): Promise<AsyncGenerator<EventItem, void, void>> {
  const response = await requestEventStream('/api/console/approval', {
    method: 'POST',
    body: JSON.stringify({ runtime_id: runtimeId, approved, approval_token: approvalToken ?? null, allow_prefix: allowPrefix?.trim() || null, guidance: guidance?.trim() || null }),
  })
  return readEventStream(response)
}

export type TerminalRequestDecisionInput = {
  runtimeId: string
  approvalToken: string
  approved: boolean
}

export async function streamDecideTerminalRequest(
  requestId: string,
  input: TerminalRequestDecisionInput,
): Promise<AsyncGenerator<EventItem, void, void>> {
  const response = await requestEventStream(
    `/api/console/terminal-requests/${encodeURIComponent(requestId)}/decision`,
    {
      method: 'POST',
      body: JSON.stringify({
        runtimeId: input.runtimeId,
        approvalToken: input.approvalToken,
        approved: input.approved,
      }),
    },
  )
  return readEventStream(response)
}
