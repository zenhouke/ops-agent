export type AssetType = 'linux' | 'local_terminal' | 'network' | 'cisco' | 'huawei' | 'juniper' | 'h3c' | 'serial'

export type AssetGroup = {
  id: number
  name: string
  description: string
  createdAt: string
  updatedAt: string
}

export type Asset = {
  id: number
  groupId: number | null
  sshKeyId: number | null
  proxyAssetId: number | null
  name: string
  assetType: AssetType
  host: string
  port: number
  username: string
  authType: string
  tags: string[]
  vendor: string
  description: string
}

export type ModelConfig = {
  id: number
  name: string
  provider: string
  baseUrl: string
  apiKeyMasked: string
  modelName: string
  isDefault: boolean
  timeoutSeconds: number
  temperature: number
  maxTokens: number
  description: string
  createdAt: string | null
  updatedAt: string | null
}

export type SSHKey = {
  id: number
  name: string
  publicKey: string
  hasPassphrase: boolean
  createdAt: string
  updatedAt: string
}

export type MCPTransport = 'stdio' | 'httpSse'

export type MCPConnectionStatus = 'untested' | 'ok' | 'failed'

export type MCPDiscoveryStatus = 'never' | 'ok' | 'failed'

export type MCPApprovalPolicy = 'allow' | 'ask' | 'deny'

export type MCPTool = {
  id: string
  originalName: string
  exposedName: string
  description: string
  inputSchema: Record<string, unknown>
  approvalPolicy: MCPApprovalPolicy
  enabled: boolean
  discovered: boolean
  lastDiscoveredAt: string | null
  createdAt: string | null
  updatedAt: string | null
}

export type MCPServer = {
  id: string
  name: string
  slug: string
  enabled: boolean
  transport: MCPTransport
  command: string
  args: string[]
  env: Record<string, string>
  url: string
  headers: Record<string, string>
  timeoutSeconds: number
  connectionStatus: MCPConnectionStatus
  discoveryStatus: MCPDiscoveryStatus
  lastError: string
  lastDiscoveredAt: string | null
  lastRefreshSucceeded: boolean
  tools: MCPTool[]
  createdAt: string | null
  updatedAt: string | null
}

export type MCPConnectionTestResult = {
  success: boolean
  message: string
  server: MCPServer | null
}

export type SkillPackage = {
  name: string
  description: string
  path: string
  valid: boolean
  error: string | null
  updatedAt: string
  bodySize: number
}

export type OpsPluginTool = {
  name: string
  exposedName: string
  description: string
  assetTypes: string[]
  inputSchema: Record<string, unknown>
}

export type OpsPlugin = {
  id: string
  name: string
  version: string
  description: string
  source: 'builtin' | 'local'
  path: string
  enabled: boolean
  valid: boolean
  error: string | null
  updatedAt: string
  tools: OpsPluginTool[]
}

export type { KnowledgeAssetRef, KnowledgeCommand, KnowledgeDraft, KnowledgeEntry, KnowledgeEntryPayload, KnowledgeGenerateDraftResponse, KnowledgeReindexResponse, KnowledgeSearchParams, KnowledgeSearchResponse, KnowledgeSourceConversation, KnowledgeSourceRef } from './knowledge'

export type SessionRecord = {
  id: number
  title: string
  model: string
}

export type TerminalStreamKind = 'echo' | 'stdout' | 'stderr' | 'status'

export type CommandStartEvent = {
  id: string
  kind: 'command_start'
  commandId: string
  runtimeId?: string
  stepId?: string
  terminalId?: string | null
  command: string
  title?: string
}

export type CommandChunkEvent = {
  id: string
  kind: 'command_chunk'
  commandId: string
  runtimeId?: string
  stepId?: string
  terminalId?: string | null
  stream: TerminalStreamKind
  text: string
  sequence?: number
}

export type CommandEndEvent = {
  id: string
  kind: 'command_end'
  commandId: string
  runtimeId?: string
  stepId?: string
  terminalId?: string | null
  exitCode: number | null
  summary?: string
}

export type ApprovalEvent = {
  id: string
  kind: 'approval_required' | 'approval_decision' | 'approval_granted' | 'approval_rejected'
  text: string
  command: string
  runtimeId?: string
  stepId?: string
  approvalToken?: string
  approved?: boolean
  status?: 'pending' | 'approved' | 'rejected'
  reason?: string
}

export type ExecutionStartedEvent = {
  id: string
  kind: 'execution_started'
  command_id: string
  terminal_id?: string | null
  command: string
  title: string
  step_id?: string
  runtimeId?: string
  stepId?: string
}

export type ExecutionOutputEvent = {
  id: string
  kind: 'execution_output'
  command_id: string
  terminal_id?: string | null
  stream: TerminalStreamKind
  text: string
  step_id?: string
  runtimeId?: string
  stepId?: string
}

export type ExecutionCompletedEvent = {
  id: string
  kind: 'execution_completed'
  command_id: string
  terminal_id?: string | null
  exit_code: number | null
  completed: boolean
  success: boolean
  step_id?: string
  runtimeId?: string
  stepId?: string
}

export type RuntimeStep = {
  stepId: string
  title: string
  command: string
  reason: string
  riskLevel: string
  workingDirectory?: string | null
  expectedOutput?: string | null
  status: 'pending' | 'running' | 'completed' | 'failed'
  output?: string
  exitCode?: number | null
}

export type RuntimeSummary = {
  runtimeId: string
  conversationId: string
  assetId: number
  terminalId: string | null
  status: string
  runState: string
  loadedSkillName: string | null
  currentStepId: string | null
  pendingApprovalStepId: string | null
  updatedAt: string
}

export type RuntimeTerminalRequest = {
  requestId: string
  runtimeId: string
  assetId: number
  assetName: string
  reason: string
  userDecisionStatus: string
  terminalCreationStatus: string
  expiresAt: string
  approvalToken: string | null
  failureReason: string | null
}

export type RuntimeTerminalAuthorization = {
  authorizationId: string
  runtimeId: string
  assetId: number
  assetName: string
  terminalId: string
  source: string
  approvedBy: string
  requestId: string | null
  status: string
  replacedByAuthorizationId: string | null
  revokeReason: string | null
}

export type RuntimeSnapshot = {
  runtimeId: string
  conversationId: string
  assetId: number
  terminalId: string | null
  status: string
  runState: string
  loadedSkillName: string | null
  steps: RuntimeStep[]
  currentStepId: string | null
  pendingApprovalStepId: string | null
  lastOutputExcerpt: string
  summary: string | null
  errorMessage: string | null
  terminalRequests: RuntimeTerminalRequest[]
  terminalAuthorizations: RuntimeTerminalAuthorization[]
  createdAt: string
  updatedAt: string
  lastSequence: number
}

export type RuntimeEventEnvelope = {
  type: string
  conversationId: string
  runtimeId: string
  sequence: number
  timestamp: string
  [key: string]: unknown
}

export type ConversationTokenUsage = {
  inputTokens: number
  outputTokens: number
  cacheCreationInputTokens: number
  cacheReadInputTokens: number
  totalTokens: number
}

export type ConversationContextStatus = {
  contextPercent: number
  contextStatus: 'normal' | 'warning' | 'critical'
  tokenUsage?: ConversationTokenUsage
  knowledgeEntriesInjected?: number
  knowledgeContextChars?: number
}

export type ContextStatusEvent = Partial<ConversationContextStatus> & {
  id: string
  kind: 'context_status'
  compactionApplied?: boolean
  fitStatus?: 'fits' | 'compacted_to_fit' | 'overflow'
  summaryRevision?: string | null
  sourceConversationRevision?: string
}

export type TerminalStatusEvent = {
  id: string
  kind: 'terminal_status'
  terminalId?: string | null
  status: string
  message?: string
}

export type TerminalAutonomyEvent = {
  id: string
  kind: 'terminal_session_request' | 'terminal_session_opened' | 'terminal_session_rejected' | 'terminal_authorization_revoked' | 'terminal_command_submitted'
  eventId?: string
  sequence?: number
  occurredAt?: string
  runtimeId?: string
  requestId?: string | null
  authorizationId?: string | null
  assetId?: number
  assetName?: string
  terminalId?: string | null
  terminalCreationStatus?: string
  approvalToken?: string | null
  channel?: string | null
  reason?: string
  revokeReason?: string
  command?: string
  approvalPolicy?: string
}

export type AgentMessage = {
  id: string
  kind: 'message'
  ts: number
  type: 'say' | 'ask'
  say?: 'text' | 'tool_use' | 'error'
  ask?: 'command' | 'followup' | 'completion_result'
  text?: string
  partial: boolean
  toolCall?: {
    id: string
    name: string
    description?: string
    displayText?: string
    kind?: string
    originalName?: string
    serverId?: string
    command?: string
    approvalToken?: string | null
    args: Record<string, any>
  }
  toolOutput?: string
  exitCode?: number
  thinking?: string
}

export type EventItem =
  | { id: string; kind: 'delta'; text: string; messageId: string; stage?: string }
  | ApprovalEvent
  | CommandStartEvent
  | CommandChunkEvent
  | CommandEndEvent
  | ExecutionStartedEvent
  | ExecutionOutputEvent
  | ExecutionCompletedEvent
  | ContextStatusEvent
  | TerminalStatusEvent
  | TerminalAutonomyEvent
  | AgentMessage
  | { id: string; kind: 'message_update'; payload: AgentMessage } // For raw event wrapper if needed
  | { id: string; kind: 'final'; text: string }
  | { id: string; kind: 'error'; text: string }
  | { id: string; kind: 'user'; text: string }

export type ConversationSummary = {
  id: string
  title: string
  selectedModel: string | null
  createdAt: string
  updatedAt: string
  eventCount: number
  lastEventKind: string | null
}

export type ConversationDetail = {
  id: string
  title: string
  selectedModel: string | null
  createdAt: string
  updatedAt: string
  events: EventItem[]
}

export type ConversationEventsPage = {
  conversation: ConversationSummary
  events: EventItem[]
  offset: number
  limit: number
  total: number
  hasMoreBefore: boolean
  hasMoreAfter: boolean
}

export type DeleteConversationResult = {
  deletedConversationId: string
  activeConversationId: string | null
}

export type AssetContext = {
  asset: Asset
  terminalSession: {
    id: number
    status: string
    lastError: string
    startedAt: string
    endedAt: string | null
  } | null
  recentTerminalEvents: Array<{
    id: number
    eventType: string
    eventData: string
    createdAt: string
  }>
  assistantSessions: SessionRecord[]
}
