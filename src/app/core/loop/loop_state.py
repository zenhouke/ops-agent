from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any, Literal

from app.shared.schemas import ModelConfig
from app.core.llm.types import LLMMessage

LoopPhase = Literal[
    "approving",
    "waiting_terminal_approval",
    "executing",
    "completed",
    "failed",
]


@dataclass(slots=True)
class LoopContext:
    runtime_id: str
    conversation_id: str
    asset_id: int
    asset_type: str
    terminal_id: str | None
    asset_summary: str
    shell_type: str
    os_type: str
    user_prompt: str
    model_config: ModelConfig
    execution_profile: str = "posix-shell"
    default_authorization_id: str | None = None
    device_vendor: str | None = None
    device_context: str = ""
    recent_output: str = ""
    conversation_history: list[LLMMessage] = field(default_factory=list)
    available_skills: list[dict[str, str]] = field(default_factory=list)
    loaded_skill_name: str | None = None
    manual_skill_name: str | None = None
    manual_skill_content: str = ""


@dataclass(slots=True)
class LoopStepResult:
    success: bool
    output: str
    exit_code: int | None = None
    completion_reason: str | None = None
    execution_id: str | None = None
    error_message: str | None = None


@dataclass(slots=True)
class LoopReviewResult:
    decision: Literal["retry", "advance", "complete"]
    summary: str = ""


@dataclass(slots=True)
class LoopRuntimeStep:
    step_id: str
    title: str
    reason: str
    risk_level: str
    working_directory: str | None = None
    expected_output: str | None = None
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    output: str = ""
    exit_code: int | None = None

@dataclass(slots=True)
class LoopState:
    phase: LoopPhase
    context: LoopContext
    messages: list[LLMMessage] = field(default_factory=list)
    pending_tool_call_id: str | None = None
    pending_tool_name: str | None = None
    pending_tool_args: dict[str, Any] | None = None
    pending_message_id: str | None = None
    pending_approval_token_hash: str | None = None
    pending_approval_token: str | None = None
    pending_approval_consistency: dict[str, Any] | None = None
    steps: list[LoopRuntimeStep] = field(default_factory=list)
    cursor: int = 0
    pending_approval_step_id: str | None = None
    retry_counts: dict[str, int] = field(default_factory=dict)
    last_output_excerpt: str = ""
    summary: str | None = None
    error_message: str | None = None
    latest_usage: dict[str, int] | None = None
    started_monotonic: float = field(default_factory=time.monotonic)
    deadline_monotonic: float | None = None
    max_llm_calls: int = 0
    max_tool_calls: int = 0
    llm_calls: int = 0
    tool_calls: int = 0
    cancel_requested: bool = False
    cancellation_reason: str | None = None

    def is_terminal(self) -> bool:
        return self.phase in {"completed", "failed"}

    def has_more_steps(self) -> bool:
        return self.cursor < len(self.steps)

    def get_current_step(self) -> LoopRuntimeStep | None:
        if 0 <= self.cursor < len(self.steps):
            return self.steps[self.cursor]
        return None

    def get_step(self, step_id: str) -> LoopRuntimeStep | None:
        return next((step for step in self.steps if step.step_id == step_id), None)
