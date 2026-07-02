from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from app.core.loop.loop_state import LoopRuntimeStep


LoopEventType = Literal[
    "message_update",  # The primary event for sync
    "plan",
    "loop_final",
    "loop_failed",
    "context_status",
    "terminal_session_request",
    "terminal_session_opened",
    "terminal_session_rejected",
    "terminal_command_submitted",
    "terminal_authorization_revoked",
    "command_start",
    "command_chunk",
    "command_end",
]


@dataclass(slots=True)
class AgentMessage:
    id: str
    ts: float
    type: Literal["say", "ask"]
    kind: str = "message"
    say: Literal["text", "tool_use", "error"] | None = None
    ask: Literal["command", "followup", "completion_result"] | None = None
    text: str = ""
    partial: bool = True
    tool_call: dict[str, Any] | None = None
    tool_output: str | None = None
    exit_code: int | None = None
    thinking: str = ""


@dataclass(slots=True)
class PlanEvent:
    id: str
    title: str
    steps: list[dict[str, Any]]
    kind: str = "plan"
    plan_id: str | None = None
    loading: bool = False
    version: int = 1
    is_latest: bool = True
    updated: bool = False
    runtime_id: str | None = None
    mode: str = "plan"
    locked_plan: bool = True


@dataclass(slots=True)
class LoopEvent:
    """Single loop event emitted via the event callback."""

    event_type: LoopEventType
    runtime_id: str
    phase: str
    payload: dict[str, Any] = field(default_factory=dict)
    message_id: str | None = None
    stage: str | None = None
    step_id: str | None = None


def emit_message_update(*, runtime_id: str, message: AgentMessage) -> LoopEvent:
    data = asdict(message)
    # Convert snake_case to camelCase for frontend
    payload = {}
    for k, v in data.items():
        if "_" in k:
            parts = k.split("_")
            camel_key = parts[0] + "".join(p.capitalize() for p in parts[1:])
            payload[camel_key] = v
        else:
            payload[k] = v

    return LoopEvent(
        event_type="message_update",
        runtime_id=runtime_id,
        phase=message.type,
        payload=payload,
    )


def emit_plan_update(*, runtime_id: str, plan_id: str, title: str, steps: list[LoopRuntimeStep], version: int, locked_plan: bool = True, is_latest: bool = True, updated: bool = False, loading: bool = False, mode: str = "plan") -> LoopEvent:
    payload = {
        "id": plan_id,
        "kind": "plan",
        "planId": plan_id,
        "title": title,
        "loading": loading,
        "version": version,
        "isLatest": is_latest,
        "updated": updated,
        "steps": [
            {
                "id": step.step_id,
                "title": step.title,
                "command": "",
                "summary": step.output or None,
                "status": step.status,
            }
            for step in steps
        ],
        "runtimeId": runtime_id,
        "mode": mode,
        "lockedPlan": locked_plan,
    }
    return LoopEvent(
        event_type="plan",
        runtime_id=runtime_id,
        phase="planning",
        payload=payload,
    )


def emit_completed(*, runtime_id: str, summary: str) -> LoopEvent:
    return LoopEvent(
        event_type="loop_final",
        runtime_id=runtime_id,
        phase="completed",
        payload={"text": summary},
    )


def emit_failed(*, runtime_id: str, error: str) -> LoopEvent:
    return LoopEvent(
        event_type="loop_failed",
        runtime_id=runtime_id,
        phase="failed",
        payload={"error": error},
    )
