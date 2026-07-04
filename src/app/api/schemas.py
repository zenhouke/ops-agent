from typing import Any, Literal

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class AssetGroupCreate(BaseModel):
    name: str
    description: str = ""


class AssetGroupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class AssetGroupView(BaseModel):
    id: int
    name: str
    description: str
    created_at: datetime
    updated_at: datetime


class AssetView(BaseModel):
    id: int
    group_id: int | None = None
    ssh_key_id: int | None = None
    proxy_asset_id: int | None = None
    name: str
    asset_type: str
    host: str
    port: int
    username: str
    auth_type: str
    tags: list[str]
    vendor: str
    description: str


class TerminalEventSummaryView(BaseModel):
    id: int
    event_type: str
    event_data: str
    created_at: datetime


class AssetContextView(BaseModel):
    asset: AssetView
    recent_terminal_events: list[TerminalEventSummaryView]


class ModelsView(BaseModel):
    provider: str
    selected_model: str
    available_models: list[str]
    model_configured: bool = True
    configuration_message: str = ""


class ModelConfigView(BaseModel):
    id: int
    name: str
    provider: str
    base_url: str
    api_key_masked: str
    model_name: str
    is_default: bool
    timeout_seconds: int = 30
    temperature: float = 0.2
    max_tokens: int = 1024
    prompt_cache_enabled: bool = True
    prompt_cache_ttl: Literal["ephemeral", "one_hour"] = "ephemeral"
    description: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ModelConfigCreate(BaseModel):
    name: str
    provider: str
    base_url: str
    api_key: SecretStr
    model_name: str = Field(min_length=1)
    is_default: bool = False
    timeout_seconds: int = 30
    temperature: float = 0.2
    max_tokens: int = 1024
    prompt_cache_enabled: bool = True
    prompt_cache_ttl: Literal["ephemeral", "one_hour"] = "ephemeral"
    description: str = ""


class ModelConfigUpdate(BaseModel):
    name: str | None = None
    provider: str | None = None
    base_url: str | None = None
    api_key: SecretStr | None = None
    model_name: str | None = Field(default=None, min_length=1)
    is_default: bool | None = None
    timeout_seconds: int | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    prompt_cache_enabled: bool | None = None
    prompt_cache_ttl: Literal["ephemeral", "one_hour"] | None = None
    description: str | None = None


class ModelConnectionTestRequest(BaseModel):
    provider: str
    base_url: str
    api_key: SecretStr
    model_name: str = Field(min_length=1)
    timeout_seconds: int = 30
    temperature: float = 0.2
    max_tokens: int = 1024
    prompt_cache_enabled: bool = True
    prompt_cache_ttl: Literal["ephemeral", "one_hour"] = "ephemeral"
    provider_options: dict[str, Any] = Field(default_factory=dict)


class ModelConnectionTestResponse(BaseModel):
    success: bool
    message: str


class ModelDiscoveryRequest(BaseModel):
    provider: str
    base_url: str
    api_key: SecretStr
    timeout_seconds: int = 30
    provider_options: dict[str, Any] = Field(default_factory=dict)


class ModelDiscoveryResponse(BaseModel):
    models: list[str]


class MCPToolView(BaseModel):
    id: str
    original_name: str
    exposed_name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    approval_policy: Literal["allow", "ask", "deny"]
    enabled: bool
    discovered: bool
    last_discovered_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class MCPServerView(BaseModel):
    id: str
    name: str
    slug: str
    enabled: bool
    transport: Literal["stdio", "http_sse"]
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int
    connection_status: Literal["untested", "ok", "failed"]
    discovery_status: Literal["never", "ok", "failed"]
    last_error: str
    last_discovered_at: str | None = None
    last_refresh_succeeded: bool
    tools: list[MCPToolView] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None


class MCPServerCreate(BaseModel):
    name: str
    transport: Literal["stdio", "http_sse"]
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = 30


class MCPServerUpdate(BaseModel):
    name: str | None = None
    transport: Literal["stdio", "http_sse"] | None = None
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    url: str | None = None
    headers: dict[str, str] | None = None
    timeout_seconds: int | None = None


class MCPServerEnableRequest(BaseModel):
    enabled: bool


class MCPToolUpdate(BaseModel):
    enabled: bool | None = None
    approval_policy: Literal["allow", "ask", "deny"] | None = None


class MCPConnectionTestResponse(BaseModel):
    success: bool
    message: str
    server: MCPServerView | None = None


class SSHKeyView(BaseModel):
    id: int
    name: str
    public_key: str
    has_passphrase: bool
    created_at: datetime
    updated_at: datetime


class AssistantMessageView(BaseModel):
    role: str
    content: str


class ChatSessionView(BaseModel):
    conversation_id: str
    asset_id: int
    model_name: str
    messages: list[AssistantMessageView]


class ChatRunRequest(BaseModel):
    conversation_id: str
    user_message: str
    asset_id: int
    model_name: str
    terminal_context: dict | None = None
    recent_messages: list[dict[str, str]] = Field(default_factory=list)


class ChatRunResponse(BaseModel):
    run_id: str
    conversation_id: str
    ui_events: list[dict]


class ChatApprovalRequest(BaseModel):
    approved: bool


class AutoApprovalRuleCreate(BaseModel):
    name: str
    asset_type: str = ""
    asset_tags: list[str] = Field(default_factory=list)
    command_name: str = ""
    command_pattern: str = ""
    max_risk_level: str = "low"
    readonly_only: bool = True
    max_duration_seconds: int = 30
    enabled: bool = True


class AutoApprovalRuleUpdate(BaseModel):
    name: str | None = None
    asset_type: str | None = None
    asset_tags: list[str] | None = None
    command_name: str | None = None
    command_pattern: str | None = None
    max_risk_level: str | None = None
    readonly_only: bool | None = None
    max_duration_seconds: int | None = None
    enabled: bool | None = None


class AutoApprovalRuleView(BaseModel):
    id: int
    conversation_id: str
    name: str
    asset_type: str
    asset_tags: list[str]
    command_name: str
    command_pattern: str
    max_risk_level: str
    readonly_only: bool
    max_duration_seconds: int
    enabled: bool
    created_at: datetime
    updated_at: datetime


class AutoApprovalMatchRequest(BaseModel):
    asset_type: str = ""
    asset_tags: list[str] = Field(default_factory=list)
    command: str
    risk_level: str = "low"
    estimated_duration_seconds: int | None = None


class AutoApprovalMatchResponse(BaseModel):
    matched: bool
    rule_id: int | None = None
    reason: str


class ApprovalRecordView(BaseModel):
    id: int
    task_id: int
    step_id: int | None
    asset_id: int | None
    terminal_id: str | None
    command: str
    working_directory: str
    risk_level: str
    llm_explanation: str
    expected_output: str
    decision: str
    operator: str
    comment: str
    created_at: datetime


class CommandExecutionView(BaseModel):
    id: int
    task_id: int
    step_id: int
    asset_id: int
    terminal_id: str
    command: str
    status: str
    approval_id: int | None
    working_directory: str
    output: str
    error_output: str
    exit_code: int | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class TaskStepRecordView(BaseModel):
    id: int
    task_id: int
    step_order: int
    title: str
    command: str
    reason: str
    working_directory: str
    expected_output: str
    risk_level: str
    status: str
    output: str
    error_message: str
    exit_code: int | None
    started_at: datetime | None
    finished_at: datetime | None


class TaskDetailView(BaseModel):
    id: int
    conversation_id: str
    parent_task_id: int | None
    run_id: str
    asset_id: int
    terminal_id: str | None
    user_input: str
    attached_terminal_context: str
    task_type: str
    risk_level: str
    status: str
    final_summary: str
    created_at: datetime
    updated_at: datetime
    steps: list[TaskStepRecordView]
    approvals: list[ApprovalRecordView]
    command_executions: list[CommandExecutionView]


class ConsoleSessionRecordView(BaseModel):
    id: int
    title: str
    model: str


class ConsoleBootstrapView(BaseModel):
    assets: list[AssetView]
    groups: list[AssetGroupView]
    historyByAsset: dict[int, list[ConsoleSessionRecordView]]
    modelOptions: list[str]
    selectedModel: str = ""
    modelConfigured: bool = True
    modelConfigurationMessage: str = ""
    sshKeys: list[SSHKeyView] = Field(default_factory=list)
    terminalSessionId: str | None = None
    terminalSessionChannel: str | None = None
    terminalSessionError: str = ""
    initialPrompt: str = ""
    terminalOutput: str = ""
    initialEvents: list[dict] = Field(default_factory=list)


class SkillPackageView(BaseModel):
    name: str
    description: str
    path: str
    valid: bool
    error: str | None = None
    updated_at: datetime
    body_size: int


class SkillsResponse(BaseModel):
    skills: list[SkillPackageView] = Field(default_factory=list)


class ConsoleRunRequest(BaseModel):
    prompt: str
    mode: Literal["agent", "plan"] = "agent"
    currentEvents: list[dict] = Field(default_factory=list)
    asset_id: int | None = None
    terminal_id: str | None = None
    conversation_id: str = "console"
    model_name: str | None = None
    selected_skill_name: str | None = None
    terminal_context: dict | None = None


class ConsoleOrchestrationResolveTargetsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    prompt: str
    current_asset_id: int | None = Field(default=None, alias="currentAssetId")
    conversation_id: str = Field(default="console", alias="conversationId")
    model_name: str | None = Field(default=None, alias="modelName")


class OrchestrationTargetPreparationView(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    asset_id: int = Field(alias="assetId")
    asset_name: str = Field(alias="assetName")
    status: str
    terminal_id: str | None = Field(default=None, alias="terminalId")
    reason: str = ""


class ConsoleOrchestrationResolveTargetsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    target_asset_ids: list[int] = Field(alias="targetAssetIds")
    target_selection_source: str = Field(alias="targetSelectionSource")
    target_selection_reason: str = Field(alias="targetSelectionReason")
    confidence: str = "medium"
    confirmation_token: str = Field(alias="confirmationToken")
    preparations: list["OrchestrationTargetPreparationView"] = Field(default_factory=list)


class ConsoleOrchestrationRunRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    prompt: str
    current_asset_id: int | None = Field(default=None, alias="currentAssetId")
    target_asset_ids: list[int] | None = Field(default=None, alias="targetAssetIds")
    confirmation_token: str | None = Field(default=None, alias="confirmationToken")
    conversation_id: str = Field(default="console", alias="conversationId")
    model_name: str | None = Field(default=None, alias="modelName")
    selected_skill_name: str | None = Field(default=None, alias="selectedSkillName")
    max_concurrency: int = Field(default=3, alias="maxConcurrency", ge=1, le=10)


class ConsoleOrchestrationApprovalRequest(BaseModel):
    runtime_id: str = Field(alias="runtimeId")
    approved: bool
    approval_token: str | None = Field(default=None, alias="approvalToken")
    allow_prefix: str | None = Field(default=None, alias="allowPrefix")


class ConsoleApprovalRequest(BaseModel):
    runtime_id: str
    approved: bool
    approval_token: str | None = None
    allow_prefix: str | None = None
    terminal_id: str | None = None


class ConsolePlanStepUpdate(BaseModel):
    id: str | None = None
    step_id: str | None = None
    title: str = Field(min_length=1)
    command: str = ""
    reason: str = "Executing plan step"
    riskLevel: str | None = None
    risk_level: str | None = None
    workingDirectory: str | None = None
    working_directory: str | None = None
    expectedOutput: str | None = None
    expected_output: str | None = None


class ConsolePlanUpdateRequest(BaseModel):
    steps: list[ConsolePlanStepUpdate]


class RuntimeStepView(BaseModel):
    step_id: str
    title: str
    command: str
    reason: str
    risk_level: str
    working_directory: str | None = None
    expected_output: str | None = None
    status: str
    output: str = ""
    exit_code: int | None = None


class RuntimePendingApprovalView(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    runtime_id: str = Field(alias="runtimeId")
    step_id: str | None = Field(default=None, alias="stepId")
    message_id: str | None = Field(default=None, alias="messageId")
    tool_call_id: str | None = Field(default=None, alias="toolCallId")
    tool_name: str | None = Field(default=None, alias="toolName")
    approval_token: str | None = Field(default=None, alias="approvalToken")
    command: str = ""
    args: dict[str, Any] = Field(default_factory=dict)


class TerminalRequestView(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    request_id: str = Field(alias="requestId")
    runtime_id: str = Field(alias="runtimeId")
    asset_id: int = Field(alias="assetId")
    asset_name: str = Field(alias="assetName")
    reason: str
    user_decision_status: str = Field(alias="userDecisionStatus")
    terminal_creation_status: str = Field(alias="terminalCreationStatus")
    expires_at: str = Field(alias="expiresAt")
    approval_token: str | None = Field(default=None, alias="approvalToken")
    failure_reason: str | None = Field(default=None, alias="failureReason")


class TerminalAuthorizationView(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    authorization_id: str = Field(alias="authorizationId")
    runtime_id: str = Field(alias="runtimeId")
    asset_id: int = Field(alias="assetId")
    asset_name: str = Field(alias="assetName")
    terminal_id: str = Field(alias="terminalId")
    source: str
    approved_by: str = Field(alias="approvedBy")
    request_id: str | None = Field(default=None, alias="requestId")
    status: str
    asset_type: str = Field(default="", alias="assetType")
    shell_type: str = Field(default="unknown", alias="shellType")
    os_type: str = Field(default="unknown", alias="osType")
    execution_profile: str = Field(default="posix-shell", alias="executionProfile")
    device_vendor: str | None = Field(default=None, alias="deviceVendor")
    replaced_by_authorization_id: str | None = Field(default=None, alias="replacedByAuthorizationId")
    revoke_reason: str | None = Field(default=None, alias="revokeReason")


class TerminalRequestDecisionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    runtime_id: str = Field(alias="runtimeId")
    approval_token: str = Field(alias="approvalToken")
    approved: bool


class TerminalRequestDecisionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str
    request_id: str = Field(alias="requestId")
    authorization_id: str | None = Field(default=None, alias="authorizationId")
    asset_id: int | None = Field(default=None, alias="assetId")
    asset_name: str | None = Field(default=None, alias="assetName")
    terminal_id: str | None = Field(default=None, alias="terminalId")
    terminal_creation_status: str | None = Field(default=None, alias="terminalCreationStatus")
    channel: str | None = None
    failure_reason: str | None = Field(default=None, alias="failureReason")


class RuntimeSummaryView(BaseModel):
    runtime_id: str
    conversation_id: str
    asset_id: int
    terminal_id: str | None = None
    status: str
    loaded_skill_name: str | None = None
    mode: str = "agent"
    plan_version: int = 1
    locked_plan: bool = False
    current_step_id: str | None = None
    pending_approval_step_id: str | None = None
    updated_at: datetime


class RuntimeSnapshotView(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    runtime_id: str
    conversation_id: str
    asset_id: int
    terminal_id: str | None = None
    status: str
    loaded_skill_name: str | None = None
    mode: str = "agent"
    plan_version: int = 1
    locked_plan: bool = False
    steps: list[RuntimeStepView] = Field(default_factory=list)
    current_step_id: str | None = None
    pending_approval_step_id: str | None = None
    last_output_excerpt: str = ""
    summary: str | None = None
    error_message: str | None = None
    pending_approval: RuntimePendingApprovalView | None = Field(default=None, alias="pendingApproval")
    terminal_requests: list[TerminalRequestView] = Field(default_factory=list, alias="terminalRequests")
    terminal_authorizations: list[TerminalAuthorizationView] = Field(default_factory=list, alias="terminalAuthorizations")
    created_at: datetime
    updated_at: datetime
    last_sequence: int = 0


class RuntimeEventView(BaseModel):
    type: str
    conversation_id: str
    runtime_id: str
    sequence: int
    timestamp: str
    payload: dict = Field(default_factory=dict)


class RuntimeEventsResponse(BaseModel):
    latest_sequence: int
    events: list[dict[str, Any]] = Field(default_factory=list)


class OrchestrationChildView(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    asset_id: int = Field(alias="assetId")
    asset_name: str = Field(alias="assetName")
    runtime_id: str | None = Field(default=None, alias="runtimeId")
    terminal_id: str | None = Field(default=None, alias="terminalId")
    status: str
    summary: str = ""
    error_message: str = Field(default="", alias="errorMessage")
    last_sequence: int = Field(default=0, alias="lastSequence")


class OrchestrationSnapshotView(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    orchestration_id: str = Field(alias="orchestrationId")
    conversation_id: str = Field(alias="conversationId")
    prompt: str
    target_asset_ids: list[int] = Field(alias="targetAssetIds")
    target_selection_source: str = Field(alias="targetSelectionSource")
    target_selection_reason: str = Field(alias="targetSelectionReason")
    confidence: str = "medium"
    status: str
    max_concurrency: int = Field(alias="maxConcurrency")
    children: list[OrchestrationChildView] = Field(default_factory=list)
    final_summary: str | None = Field(default=None, alias="finalSummary")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    last_sequence: int = Field(default=0, alias="lastSequence")


class OrchestrationEventsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    latest_sequence: int = Field(alias="latestSequence")
    events: list[dict[str, Any]] = Field(default_factory=list)


class ConversationSummaryView(BaseModel):
    id: str
    title: str
    selected_model: str | None = None
    created_at: datetime
    updated_at: datetime
    event_count: int
    last_event_kind: str | None = None


class ConversationDetailView(BaseModel):
    id: str
    title: str
    selected_model: str | None = None
    created_at: datetime
    updated_at: datetime
    events: list[dict] = Field(default_factory=list)


class ConversationCreateRequest(BaseModel):
    selected_model: str | None = None


class ConversationCreateResponse(BaseModel):
    conversation: ConversationSummaryView
    events: list[dict] = Field(default_factory=list)


class ConversationTokenUsageView(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    total_tokens: int = 0


class ConversationContextStatusView(BaseModel):
    context_percent: int
    context_status: Literal["normal", "warning", "critical"]
    token_usage: ConversationTokenUsageView = Field(default_factory=ConversationTokenUsageView)


class ConversationAppendEventsRequest(BaseModel):
    events: list[dict] = Field(default_factory=list)


class ConversationAppendEventsResponse(BaseModel):
    conversation: ConversationSummaryView
    appended_count: int = 0


class ConversationEventsPageView(BaseModel):
    conversation: ConversationSummaryView
    events: list[dict] = Field(default_factory=list)
    offset: int
    limit: int
    total: int
    has_more_before: bool
    has_more_after: bool


class PendingApprovalStepView(BaseModel):
    title: str
    command: str
    reason: str
    risk_level: str
    working_directory: str = ""
    expected_output: str = ""


class PendingApprovalView(BaseModel):
    task_id: int
    run_id: str
    conversation_id: str
    status: str
    message: str
    latest_decision: str | None = None
    steps: list[PendingApprovalStepView]


class SerialPortView(BaseModel):
    device: str
    description: str
    hwid: str
    name: str | None = None
    vid: int | None = None
    pid: int | None = None
    serial_number: str | None = None
    location: str | None = None
    manufacturer: str | None = None
    product: str | None = None
    interface: str | None = None


class KnowledgeCommandView(BaseModel):
    command: str = ""
    purpose: str = ""
    outcome: str = ""


class KnowledgeAssetRefView(BaseModel):
    assetId: int | None = None
    label: str = ""


class KnowledgeSourceRefView(BaseModel):
    conversationId: str | None = None
    eventId: str | None = None
    eventIndex: int | None = None
    eventType: str = ""
    quote: str = ""
    relevance: str = ""


class KnowledgeSourceConversationView(BaseModel):
    id: str | None = None
    title: str = ""
    updatedAt: str | None = None


class KnowledgeDraftView(BaseModel):
    title: str = ""
    summary: str = ""
    problem: str = ""
    diagnosis: str = ""
    resolution: str = ""
    commands: list[KnowledgeCommandView] = Field(default_factory=list)
    assets: list[KnowledgeAssetRefView] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    sources: list[KnowledgeSourceRefView] = Field(default_factory=list)
    redactionWarnings: list[str] = Field(default_factory=list)


class KnowledgeGenerateDraftRequest(BaseModel):
    maxSourceEvents: int = 120
    modelName: str | None = None


class KnowledgeGenerateDraftResponse(BaseModel):
    draft: KnowledgeDraftView
    sourceConversation: KnowledgeSourceConversationView


class KnowledgeEntryCreateRequest(BaseModel):
    title: str = ""
    summary: str = ""
    problem: str = ""
    diagnosis: str = ""
    resolution: str = ""
    commands: list[KnowledgeCommandView] = Field(default_factory=list)
    assets: list[KnowledgeAssetRefView] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    sources: list[KnowledgeSourceRefView] = Field(default_factory=list)
    redactionWarnings: list[str] = Field(default_factory=list)
    sourceConversationId: str | None = None
    sourceConversationTitle: str = ""
    sourceConversationUpdatedAt: str | None = None


class KnowledgeEntryUpdateRequest(BaseModel):
    title: str = ""
    summary: str = ""
    problem: str = ""
    diagnosis: str = ""
    resolution: str = ""
    commands: list[KnowledgeCommandView] = Field(default_factory=list)
    assets: list[KnowledgeAssetRefView] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    sources: list[KnowledgeSourceRefView] = Field(default_factory=list)
    redactionWarnings: list[str] = Field(default_factory=list)
    sourceConversationId: str | None = None
    sourceConversationTitle: str = ""
    sourceConversationUpdatedAt: str | None = None


class KnowledgeEntryView(BaseModel):
    id: str
    title: str
    summary: str = ""
    problem: str = ""
    diagnosis: str = ""
    resolution: str = ""
    commands: list[KnowledgeCommandView] = Field(default_factory=list)
    assets: list[KnowledgeAssetRefView] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    sources: list[KnowledgeSourceRefView] = Field(default_factory=list)
    sourceConversation: KnowledgeSourceConversationView = Field(default_factory=KnowledgeSourceConversationView)
    createdAt: str
    updatedAt: str


class KnowledgeSearchResponse(BaseModel):
    items: list[KnowledgeEntryView] = Field(default_factory=list)
    total: int = 0
    limit: int = 20
    offset: int = 0


class KnowledgeReindexResponse(BaseModel):
    indexed: int = 0
    failed: int = 0
