from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from app.core.loop.loop_events import LoopEvent
from app.core.loop.loop_state import LoopState
from app.core.loop.message_manager import MessageManager
from app.core.tool.handler import ToolDisplayMetadata
from app.core.tool.schema import LLMToolDefinition


class McpToolHandler:
    def __init__(self, *, definition: LLMToolDefinition, original_name: str, server_id: str,
                 approval_policy: str, call: Callable[[dict[str, Any]], tuple[bool, str]]) -> None:
        self._definition = definition
        self._original_name = original_name
        self._server_id = server_id
        self._approval_policy = approval_policy
        self._call = call

    @property
    def definition(self) -> LLMToolDefinition:
        return self._definition

    def needs_approval(self, args: dict[str, Any]) -> tuple[str, str]:
        _ = args
        if self._approval_policy == "allow":
            return "allow", "MCP tool policy allows execution."
        if self._approval_policy == "deny":
            return "deny", "MCP tool policy denies execution."
        return "ask", "MCP tool requires operator approval."

    def display_metadata(self, args: dict[str, Any]) -> ToolDisplayMetadata:
        _ = args
        return ToolDisplayMetadata(
            description=self._definition.description or f"MCP tool {self._original_name}",
            display_text=f"Call MCP tool {self._definition.name}",
            extra={
                "kind": "mcp",
                "originalName": self._original_name,
                "serverId": self._server_id,
            },
        )

    def execute(
        self,
        *,
        state: LoopState,
        step_id: str,
        args: dict[str, Any],
        manager: MessageManager | None = None,
    ) -> Iterator[LoopEvent]:
        _ = state, step_id
        ok, output = self._call(args)
        if manager:
            yield from manager.update(tool_output=output)
        return ok, output
