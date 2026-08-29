from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from app.core.loop.loop_events import LoopEvent
from app.core.loop.loop_state import LoopState
from app.core.loop.message_manager import MessageManager
from app.core.tool.handler import ToolDisplayMetadata
from app.core.tool.schema import LLMToolDefinition


class AskFollowupHandler:
    """Control tool used by AgentLoop to pause for missing user input."""

    @property
    def definition(self) -> LLMToolDefinition:
        return LLMToolDefinition(
            name="ask_followup",
            description=(
                "Ask the operator one concise question when a material target, scope, constraint, "
                "or desired outcome is missing. This pauses the runtime until the operator replies."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The single, concrete question the operator must answer.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why the answer is required before continuing.",
                    },
                },
                "required": ["question"],
            },
        )

    def needs_approval(self, args: dict[str, Any]) -> tuple[str, str]:
        _ = args
        return "allow", "Asking a question does not change external state."

    def display_metadata(self, args: dict[str, Any]) -> ToolDisplayMetadata:
        return ToolDisplayMetadata(
            description=str(args.get("reason") or "More information is required."),
            display_text=str(args.get("question") or "Ask the operator a follow-up question"),
            extra={"kind": "followup"},
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
        return True, "Follow-up question emitted by AgentLoop."
