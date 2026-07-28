from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.api.schemas.resources import AssetGroupView, AssetView, SSHKeyView
from app.api.schemas.runtime import SkillPackageView


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
    sshKeys: list[SSHKeyView] = Field(default_factory=list)
    terminalSessionId: str | None = None
    terminalSessionChannel: str | None = None
    terminalSessionError: str = ""
    initialPrompt: str = ""
    terminalOutput: str = ""
    initialEvents: list[dict] = Field(default_factory=list)
