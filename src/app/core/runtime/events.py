from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, TypedDict, cast


RuntimeEventType = Literal[
    "approval_required",
    "approval_resolved",
    "execution_started",
    "execution_output",
    "execution_completed",
    "task_waiting_input",
    "task_completed",
    "task_failed",
]


class RuntimeEvent(TypedDict):
    type: RuntimeEventType
    conversation_id: str
    runtime_id: str
    sequence: int
    timestamp: str


def build_runtime_event(
    event_type: RuntimeEventType,
    *,
    conversation_id: str,
    runtime_id: str,
    sequence: int,
    **payload: Any,
) -> RuntimeEvent:
    base: dict[str, Any] = {
        "type": event_type,
        "conversation_id": conversation_id,
        "runtime_id": runtime_id,
        "sequence": sequence,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    base.update(payload)
    return cast(RuntimeEvent, base)
