from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from collections.abc import Callable
from typing import Literal


ExecutionEventType = Literal["started", "output", "completed"]
CompletionReason = Literal[
    "exit_code",
    "prompt_detected",
    "pager_end",
    "timeout",
    "mode_changed",
    "manual_stop",
    "unsupported",
]


@dataclass(slots=True)
class ExecutionContext:
    working_directory: str | None = None
    timeout_seconds: float | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    cancel_check: Callable[[], bool] | None = None


@dataclass(slots=True)
class ExecutionEvent:
    execution_id: str
    event_type: ExecutionEventType
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    stream: str = "stdout"
    text: str = ""
    exit_code: int | None = None
    completed: bool = False
    success: bool = False
    needs_attention: bool = False
    completion_reason: CompletionReason | None = None
    mode: str | None = None
    pager_detected: bool = False
    profile: str = "posix-shell"
    prompt_before: str | None = None
    prompt_after: str | None = None
    matched_error: str | None = None


@dataclass(slots=True)
class ExecutionResult:
    execution_id: str
    output: str
    completed: bool
    success: bool
    needs_attention: bool = False
    exit_code: int | None = None
    completion_reason: CompletionReason | None = None
    mode: str | None = None
    pager_detected: bool = False
    profile: str = "posix-shell"
    prompt_before: str | None = None
    prompt_after: str | None = None
    matched_error: str | None = None
