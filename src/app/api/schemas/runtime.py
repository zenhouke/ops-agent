from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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
    mode: Literal["standard", "incident"] = "standard"
    currentEvents: list[dict] = Field(default_factory=list)
    asset_id: int | None = None
    terminal_id: str | None = None
    conversation_id: str = "console"
    user_event_id: str | None = Field(default=None, pattern=r"^user-[A-Za-z0-9_-]{8,100}$")
    model_name: str | None = None
    selected_skill_name: str | None = None
    terminal_context: dict | None = None


class ConsoleApprovalRequest(BaseModel):
    runtime_id: str
    approved: bool
    approval_token: str | None = None
    allow_prefix: str | None = None
    guidance: str | None = None


class RuntimeMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)


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


class AgentTaskStateView(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    goal: str = ""
    current_request: str = Field(default="", alias="currentRequest")
    scope: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list, alias="acceptanceCriteria")
    verified_facts: list[str] = Field(default_factory=list, alias="verifiedFacts")
    decisions: list[str] = Field(default_factory=list)
    open_items: list[str] = Field(default_factory=list, alias="openItems")
    completed_items: list[str] = Field(default_factory=list, alias="completedItems")
    revision: int = 1


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
    scope_expansion_required: bool = Field(default=False, alias="scopeExpansionRequired")


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
    scope_expansion_required: bool = Field(default=False, alias="scopeExpansionRequired")


class RuntimeSummaryView(BaseModel):
    runtime_id: str
    conversation_id: str
    asset_id: int
    terminal_id: str | None = None
    status: str
    run_state: str = "queued"
    loaded_skill_name: str | None = None
    current_step_id: str | None = None
    pending_approval_step_id: str | None = None
    updated_at: datetime


class RuntimeSnapshotView(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    runtime_id: str
    conversation_id: str
    asset_id: int
    conversation_scope_mode: Literal["single", "multi"] = "single"
    conversation_primary_asset_id: int | None = None
    allowed_asset_ids: list[int] = Field(default_factory=list)
    terminal_id: str | None = None
    status: str
    run_state: str = "queued"
    loaded_skill_name: str | None = None
    task_state: AgentTaskStateView = Field(default_factory=AgentTaskStateView)
    steps: list[RuntimeStepView] = Field(default_factory=list)
    current_step_id: str | None = None
    pending_approval_step_id: str | None = None
    pending_approval_token: str | None = None
    pending_followup_question: str | None = None
    pending_user_message_count: int = 0
    last_output_excerpt: str = ""
    summary: str | None = None
    error_message: str | None = None
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


class ConversationSummaryView(BaseModel):
    id: str
    title: str
    selected_model: str | None = None
    created_at: datetime
    updated_at: datetime
    event_count: int
    last_event_kind: str | None = None
    asset_id: int | None = None
    scope_mode: Literal["single", "multi"] = "single"
    allowed_asset_ids: list[int] = Field(default_factory=list)


class ConversationDetailView(BaseModel):
    id: str
    title: str
    selected_model: str | None = None
    created_at: datetime
    updated_at: datetime
    events: list[dict] = Field(default_factory=list)
    asset_id: int | None = None
    scope_mode: Literal["single", "multi"] = "single"
    allowed_asset_ids: list[int] = Field(default_factory=list)


class ConversationCreateRequest(BaseModel):
    selected_model: str | None = None
    asset_id: int = 0
    scope_mode: Literal["single", "multi"] = "single"


class ConversationCreateResponse(BaseModel):
    conversation: ConversationSummaryView
    events: list[dict] = Field(default_factory=list)


class ConversationRewriteRequest(BaseModel):
    before_event_id: str


class ConversationRewriteResponse(BaseModel):
    conversation: ConversationSummaryView
    events: list[dict] = Field(default_factory=list)


class ConversationTokenUsageView(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    total_tokens: int = 0
    measurement: Literal["reported", "unavailable"] = "unavailable"


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
