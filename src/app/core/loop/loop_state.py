from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.shared.schemas import ModelConfig, PlanStep
from app.core.llm.types import LLMMessage

LoopMode = Literal["agent", "plan"]


LoopPhase = Literal[
    "planning",
    "waiting_plan_approval",
    "approving",
    "waiting_terminal_approval",
    "executing",
    "completed",
    "failed",
    "cancelled",
]


LoopDecision = Literal[
    "continue",
    "retry",
    "replan",
    "complete",
    "fail",
    "wait_approval",
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
    mode: LoopMode = "agent"
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

    @classmethod
    def from_plan_step(cls, *, step_id: str, step: PlanStep, status: str = "pending") -> "LoopRuntimeStep":
        return cls(
            step_id=step_id,
            title=step.title,
            reason=step.reason,
            risk_level=step.risk_level,
            working_directory=step.working_directory or None,
            expected_output=step.expected_output or None,
            status=status,  # type: ignore[arg-type]
        )

    def to_plan_step(self) -> PlanStep:
        return PlanStep(
            title=self.title,
            reason=self.reason,
            risk_level=self.risk_level,
            working_directory=self.working_directory or "",
            expected_output=self.expected_output or "",
        )


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
    plan_version: int = 1
    locked_plan: bool = False
    pending_approval_step_id: str | None = None
    pending_patch: dict[str, Any] | None = None
    retry_counts: dict[str, int] = field(default_factory=dict)
    last_output_excerpt: str = ""
    summary: str | None = None
    error_message: str | None = None
    latest_usage: dict[str, int] | None = None
    cancel_requested: bool = False

    def is_terminal(self) -> bool:
        return self.phase in {"completed", "failed", "cancelled"}

    def has_more_steps(self) -> bool:
        return self.cursor < len(self.steps)

    def get_current_step(self) -> LoopRuntimeStep | None:
        if 0 <= self.cursor < len(self.steps):
            return self.steps[self.cursor]
        return None

    def get_step(self, step_id: str) -> LoopRuntimeStep | None:
        return next((step for step in self.steps if step.step_id == step_id), None)

    def get_remaining_plan_steps(self) -> list[PlanStep]:
        return [step.to_plan_step() for step in self.steps[self.cursor + 1:]]
