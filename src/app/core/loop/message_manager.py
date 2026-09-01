from __future__ import annotations

import time
import uuid
from typing import Any, Iterator, Literal

from app.core.loop.loop_events import AgentMessage, LoopEvent, emit_message_delta, emit_message_update


class MessageManager:
    """Manages the state of the current AgentMessage and yields updates."""

    def __init__(self, runtime_id: str) -> None:
        self.runtime_id = runtime_id
        self.current_message: AgentMessage | None = None

    def begin_message(
        self,
        *,
        message_type: Literal["say", "ask"],
        say_type: Literal["text", "tool_use", "error"] | None = None,
        ask_type: Literal["command", "followup", "completion_result"] | None = None,
    ) -> Iterator[LoopEvent]:
        """Start a new message and yield initial update."""
        self.current_message = AgentMessage(
            id=f"msg-{uuid.uuid4().hex[:8]}",
            ts=time.time(),
            type=message_type,
            say=say_type,
            ask=ask_type,
            partial=True,
        )
        yield self._emit()

    def update(
        self,
        *,
        text: str | None = None,
        thinking: str | None = None,
        tool_output: str | None = None,
        tool_call: dict[str, Any] | None = None,
        exit_code: int | None = None,
        partial: bool | None = None,
    ) -> Iterator[LoopEvent]:
        """Update the current message and yield snapshot."""
        if not self.current_message:
            return

        if text is not None:
            self.current_message.text += text
        if thinking is not None:
            self.current_message.thinking += thinking
        if tool_output is not None:
            if self.current_message.tool_output is None:
                self.current_message.tool_output = ""
            self.current_message.tool_output += tool_output
        if tool_call is not None:
            self.current_message.tool_call = tool_call
        if exit_code is not None:
            self.current_message.exit_code = exit_code
        if partial is not None:
            self.current_message.partial = partial

        if (
            text is not None
            and thinking is None
            and tool_output is None
            and tool_call is None
            and exit_code is None
            and partial is None
        ):
            yield emit_message_delta(
                runtime_id=self.runtime_id,
                message_id=self.current_message.id,
                text=text,
            )
            return

        yield self._emit()

    def replace_text(self, text: str) -> Iterator[LoopEvent]:
        """Replace streamed text when the completed response fails validation."""
        if not self.current_message:
            return
        self.current_message.text = text
        yield self._emit()

    def finalize(
        self,
        *,
        text: str | None = None,
        tool_call: dict[str, Any] | None = None,
        exit_code: int | None = None,
    ) -> Iterator[LoopEvent]:
        """Mark the current message as finished and yield final snapshot."""
        if not self.current_message:
            return
        if text is not None:
            self.current_message.text += text
        if tool_call is not None:
            self.current_message.tool_call = tool_call
        if exit_code is not None:
            self.current_message.exit_code = exit_code
        self.current_message.partial = False
        self._last_finalized_id = self.current_message.id
        yield self._emit()
        self.current_message = None

    def resume_message(
        self,
        *,
        message_id: str,
        message_type: Literal["say", "ask"] = "say",
        say_type: Literal["text", "tool_use", "error"] | None = None,
    ) -> Iterator[LoopEvent]:
        """Resume an existing message by ID, transitioning its type.

        Used after approval: the ask message becomes a say/tool_use message,
        keeping the same ID so the frontend replaces the card in-place.
        """
        self.current_message = AgentMessage(
            id=message_id,
            ts=time.time(),
            type=message_type,
            say=say_type,
            partial=True,
        )
        yield self._emit()

    def mark_ask_as_processed(self, *, message_id: str) -> Iterator[LoopEvent]:
        """Mark an ask message as processed by changing its type to 'asked'.
        
        This preserves the original ask message in the conversation history
        but indicates it has been handled (approved or rejected).
        """
        processed_message = AgentMessage(
            id=message_id,
            ts=time.time(),
            type="asked",  # type: ignore - 'asked' is a custom type for processed ask messages
            partial=False,
        )
        yield emit_message_update(runtime_id=self.runtime_id, message=processed_message)

    @property
    def last_finalized_id(self) -> str | None:
        return getattr(self, "_last_finalized_id", None)

    def _emit(self) -> LoopEvent:
        assert self.current_message is not None
        return emit_message_update(runtime_id=self.runtime_id, message=self.current_message)
