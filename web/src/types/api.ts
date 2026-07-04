import type { Asset, AssetGroup, EventItem, KnowledgeAssetRef, KnowledgeCommand, KnowledgeDraft, KnowledgeEntry, KnowledgeGenerateDraftResponse, KnowledgeReindexResponse, KnowledgeSearchResponse, KnowledgeSourceConversation, KnowledgeSourceRef, RunMode, RuntimeSnapshot, RuntimeSummary, SessionRecord, SSHKey, SkillPackage } from './ops'

export type { RunMode }

export type ConversationSummaryDto = {
  id: string
  title: string
  selected_model: string | null
  created_at: string
  updated_at: string
  event_count: number
  last_event_kind: string | null
}

export type ConversationDetailDto = {
  id: string
  title: string
  selected_model: string | null
  created_at: string
  updated_at: string
  events: EventItem[]
}

export type ConversationEventsPageDto = {
  conversation: ConversationSummaryDto
  events: EventItem[]
  offset: number
  limit: number
  total: number
  has_more_before: boolean
  has_more_after: boolean
}

export type ConversationAppendEventsResponseDto = {
  conversation: ConversationSummaryDto
  appended_count: number
}

export type ConversationCreateResponseDto = {
  conversation: ConversationSummaryDto
  events: EventItem[]
}

export type ConversationTokenUsageDto = {
  input_tokens: number
  output_tokens: number
  cache_creation_input_tokens: number
  cache_read_input_tokens: number
  total_tokens: number
}

export type ConversationContextStatusDto = {
  context_percent: number
  context_status: 'normal' | 'warning' | 'critical'
  token_usage?: ConversationTokenUsageDto
}

export type SkillPackageDto = {
  name: string
  description: string
  path: string
  valid: boolean
  error: string | null
  updated_at: string
  body_size: number
}

export type SkillsResponseDto = {
  skills: SkillPackageDto[]
}

export type ConsoleRunRequest = {
  prompt: string
  mode: RunMode
  assetId?: number
  terminalId?: string | null
  modelName?: string
  conversationId?: string
  selectedSkillName?: string | null
}

export type ConsoleRunRequestDto = {
  prompt: string
  mode: RunMode
  asset_id?: number
  terminal_id?: string | null
  model_name?: string
  conversation_id?: string
  selected_skill_name?: string
}

export type ConsoleOrchestrationResolveTargetsRequest = {
  prompt: string
  currentAssetId?: number | null
  conversationId: string
  modelName?: string | null
}

export type ConsoleOrchestrationResolveTargetsResponseDto = {
  targetAssetIds: number[]
  targetSelectionSource: string
  targetSelectionReason: string
  confidence: 'high' | 'medium' | 'low'
  confirmationToken: string
  preparations: OrchestrationTargetPreparationDto[]
}

export type ConsoleOrchestrationRunRequest = {
  prompt: string
  currentAssetId?: number | null
  targetAssetIds?: number[] | null
  confirmationToken?: string | null
  conversationId: string
  modelName?: string | null
  selectedSkillName?: string | null
  maxConcurrency?: number
}

export type OrchestrationChildDto = {
  assetId: number
  assetName: string
  runtimeId: string | null
  terminalId: string | null
  status: string
  summary: string
  errorMessage: string
  lastSequence: number
}

export type OrchestrationTargetPreparationDto = {
  assetId: number
  assetName: string
  status: 'ready' | 'needs_terminal' | 'unavailable'
  terminalId: string | null
  reason: string
}

export type OrchestrationSnapshotDto = {
  orchestrationId: string
  conversationId: string
  prompt: string
  targetAssetIds: number[]
  targetSelectionSource: string
  targetSelectionReason: string
  confidence: 'high' | 'medium' | 'low'
  status: string
  maxConcurrency: number
  children: OrchestrationChildDto[]
  finalSummary: string | null
  createdAt: string
  updatedAt: string
  lastSequence: number
}

export type OrchestrationEventsResponseDto = {
  latestSequence: number
  events: Array<Record<string, unknown>>
}

export type SkillsApiModels = {
  skills: SkillPackage[]
}

export type ConsoleBootstrap = {
  assets: Asset[]
  groups: AssetGroup[]
  historyByAsset: Record<number, SessionRecord[]>
  modelOptions: string[]
  selectedModel: string
  modelConfigured: boolean
  modelConfigurationMessage: string
  terminalSessionId: string | null
  terminalSessionChannel: string | null
  terminalSessionError: string
  initialPrompt: string
  terminalOutput: string
  initialEvents: EventItem[]
  sshKeys: SSHKey[]
}

export type RuntimeSummaryDto = {
  runtime_id: string
  conversation_id: string
  asset_id: number
  terminal_id: string | null
  status: string
  mode: RunMode
  plan_version: number
  locked_plan: boolean
  loaded_skill_name: string | null
  current_step_id: string | null
  pending_approval_step_id: string | null
  updated_at: string
}

export type RuntimeSnapshotDto = {
  runtime_id: string
  conversation_id: string
  asset_id: number
  terminal_id: string | null
  status: string
  mode: RunMode
  plan_version: number
  locked_plan: boolean
  loaded_skill_name: string | null
  steps: Array<{
    step_id: string
    title: string
    command: string
    reason: string
    risk_level: string
    working_directory?: string | null
    expected_output?: string | null
    status: 'pending' | 'running' | 'completed' | 'failed'
    output?: string
    exit_code?: number | null
  }>
  current_step_id: string | null
  pending_approval_step_id: string | null
  last_output_excerpt: string
  summary: string | null
  error_message: string | null
  pendingApproval?: {
    runtimeId: string
    stepId?: string | null
    messageId?: string | null
    toolCallId?: string | null
    toolName?: string | null
    approvalToken?: string | null
    command: string
    args: Record<string, unknown>
  } | null
  terminalRequests?: Array<{
    requestId: string
    runtimeId: string
    assetId: number
    assetName: string
    reason: string
    userDecisionStatus: string
    terminalCreationStatus: string
    expiresAt: string
    approvalToken?: string | null
    failureReason?: string | null
  }>
  terminalAuthorizations?: Array<{
    authorizationId: string
    runtimeId: string
    assetId: number
    assetName: string
    terminalId: string
    source: string
    approvedBy: string
    requestId?: string | null
    status: string
    replacedByAuthorizationId?: string | null
    revokeReason?: string | null
  }>
  created_at: string
  updated_at: string
  last_sequence: number
}

export type RuntimeEventsResponseDto = {
  latest_sequence: number
  events: Array<Record<string, unknown>>
}

export type RuntimeApiModels = {
  summary: RuntimeSummary
  snapshot: RuntimeSnapshot
}

export type KnowledgeCommandDto = KnowledgeCommand

export type KnowledgeAssetRefDto = KnowledgeAssetRef

export type KnowledgeSourceRefDto = KnowledgeSourceRef

export type KnowledgeSourceConversationDto = KnowledgeSourceConversation

export type KnowledgeDraftDto = KnowledgeDraft

export type KnowledgeEntryDto = KnowledgeEntry

export type KnowledgeSearchResponseDto = KnowledgeSearchResponse

export type KnowledgeReindexResponseDto = KnowledgeReindexResponse

export type KnowledgeGenerateDraftResponseDto = KnowledgeGenerateDraftResponse

export type KnowledgeEntryPayloadDto = KnowledgeDraftDto & {
  sourceConversationId?: string | null
  sourceConversationTitle?: string
  sourceConversationUpdatedAt?: string | null
}

export type KnowledgeGenerateDraftRequestDto = {
  maxSourceEvents?: number
  modelName?: string | null
}
