from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from app.core.loop.loop_events import LoopEvent
from app.core.loop.loop_state import LoopState
from app.core.loop.message_manager import MessageManager
from app.core.tool.handler import ToolDisplayMetadata
from app.core.tool.schema import LLMToolDefinition


class UpdateTaskStateHandler:
    @property
    def definition(self) -> LLMToolDefinition:
        list_property = {"type": "array", "items": {"type": "string"}}
        return LLMToolDefinition(
            name="update_task_state",
            description=(
                "Update the shared task state when the goal, scope, constraints, acceptance criteria, verified facts, "
                "operator decisions, or open/completed items materially change. Send complete replacement lists for "
                "fields you update. Never put hypotheses in verified_facts."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "goal": {"type": "string"},
                    "scope": list_property,
                    "constraints": list_property,
                    "acceptance_criteria": list_property,
                    "verified_facts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Verified facts only, each ending with a concise source reference such as '(source: command output)' or '(source: operator)'.",
                    },
                    "decisions": list_property,
                    "open_items": list_property,
                    "completed_items": list_property,
                },
                "minProperties": 1,
            },
        )

    def needs_approval(self, args: dict[str, Any]) -> tuple[str, str]:
        _ = args
        return "allow", "Updating in-memory task state does not change external systems."

    def display_metadata(self, args: dict[str, Any]) -> ToolDisplayMetadata:
        _ = args
        return ToolDisplayMetadata(
            description="Update the shared goal, constraints, facts, and progress.",
            display_text="Update task state",
            extra={"kind": "task_state"},
        )

    def execute(
        self,
        *,
        state: LoopState,
        step_id: str,
        args: dict[str, Any],
        manager: MessageManager | None = None,
    ) -> Iterator[LoopEvent]:
        _ = state, step_id, args, manager
        if False:
            yield
        return True, "Task state update emitted by AgentLoop."
