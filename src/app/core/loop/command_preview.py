from collections.abc import Iterator

from app.core.llm.types import LLMToolCall
from app.core.loop.loop_events import LoopEvent
from app.core.loop.message_manager import MessageManager


class CommandPreviewMessages:
    """Display draft commands only; these messages never authorize execution."""

    def __init__(self, runtime_id: str):
        self.runtime_id = runtime_id
        self.messages: dict[str, MessageManager] = {}

    def update(self, call: LLMToolCall, *, has_explanation: bool) -> Iterator[LoopEvent]:
        command = call.arguments.get("command")
        explanation = call.arguments.get("explanation")
        if call.name != "execute_command" or not isinstance(command, str) or not command:
            return
        if not has_explanation and not (isinstance(explanation, str) and explanation.strip()):
            return
        manager = self.messages.get(call.id)
        if manager is None:
            if not has_explanation:
                purpose = MessageManager(self.runtime_id)
                yield from purpose.begin_message(message_type="say", say_type="text")
                yield from purpose.finalize(text=str(explanation))
            manager = MessageManager(self.runtime_id)
            self.messages[call.id] = manager
            yield from manager.begin_message(message_type="say", say_type="tool_use")
        payload = {
            "id": call.id, "name": call.name, "kind": "command",
            "command": command, "args": dict(call.arguments), "generationState": "generating",
        }
        if manager.current_message and manager.current_message.tool_call != payload:
            yield from manager.update(tool_call=payload)

    def finish(self) -> Iterator[LoopEvent]:
        for manager in self.messages.values():
            if manager.current_message:
                payload = dict(manager.current_message.tool_call or {})
                # A completed draft still requires validation and an approval token.
                payload["generationState"] = "not_submitted"
                yield from manager.finalize(tool_call=payload)

    def message_id(self, tool_call_id: str) -> str | None:
        manager = self.messages.get(tool_call_id)
        return manager.last_finalized_id if manager else None
