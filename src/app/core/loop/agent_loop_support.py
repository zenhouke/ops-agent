from __future__ import annotations

import re
from typing import Any

from app.core.llm.types import LLMMessage, LLMTokenUsage
from app.core.loop.loop_state import LoopState
from app.core.loop.state_machine import clear_pending_approval_state
from app.core.tool.handler import ToolDisplayMetadata, ToolHandler


_SECRET_ARG_KEY_RE = re.compile(
    r"(token|password|passwd|secret|api[_-]?key|authorization|cookie|credential)",
    re.IGNORECASE,
)


class AgentLoopSupportMixin:
    def _get_tool_display_metadata(
        self: Any,
        handler: ToolHandler | None,
        args: dict[str, Any],
    ) -> ToolDisplayMetadata:
        if handler is None:
            return ToolDisplayMetadata()
        display_metadata = getattr(handler, "display_metadata", None)
        return display_metadata(args) if display_metadata is not None else ToolDisplayMetadata()

    def _args_for_display(
        self: Any,
        handler: ToolHandler | None,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        metadata = self._get_tool_display_metadata(handler, args)
        return self._redact_sensitive_args(args) if metadata.extra.get("kind") == "mcp" else args

    def _redact_sensitive_args(self: Any, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: "[redacted]" if _SECRET_ARG_KEY_RE.search(str(key)) else self._redact_sensitive_args(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._redact_sensitive_args(item) for item in value]
        return value

    def _clear_pending_approval(self: Any, state: LoopState) -> None:
        clear_pending_approval_state(state)

    def _append_pending_tool_result(self: Any, state: LoopState, *, content: str) -> None:
        message = LLMMessage(
            role="tool",
            content=content,
            tool_call_id=state.pending_tool_call_id,
            name=state.pending_tool_name,
        )
        pending_tool_call_id = state.pending_tool_call_id
        if pending_tool_call_id is None:
            state.messages.append(message)
            return
        for index in range(len(state.messages) - 1, -1, -1):
            candidate = state.messages[index]
            if candidate.role != "assistant":
                continue
            tool_call_ids = [tool_call.id for tool_call in candidate.tool_calls]
            if pending_tool_call_id not in tool_call_ids:
                continue
            insert_at = index + 1
            for tool_call_id in tool_call_ids:
                if tool_call_id == pending_tool_call_id:
                    break
                while insert_at < len(state.messages):
                    existing = state.messages[insert_at]
                    if existing.role == "tool" and existing.tool_call_id == tool_call_id:
                        insert_at += 1
                        break
                    if existing.role == "tool":
                        insert_at += 1
                        continue
                    break
            state.messages.insert(insert_at, message)
            return
        state.messages.append(message)

    def _build_approval_consistency(
        self: Any,
        state: LoopState,
        args: dict[str, Any],
        tool_call_id: str,
    ) -> dict[str, Any] | None:
        authorization_id = str(args.get("authorization_id", "") or "")
        handler = self._tools.get("execute_command")
        terminal = getattr(handler, "_terminal", None)
        resolver = getattr(terminal, "resolve_terminal_authorization", None)
        if not authorization_id or resolver is None:
            raise ValueError("Missing terminal authorization resolver.")
        authorization = resolver(state.context.runtime_id, authorization_id)
        return {
            "runtime_id": state.context.runtime_id,
            "conversation_id": state.context.conversation_id,
            "tool_call_id": tool_call_id,
            "authorization_id": authorization.authorization_id,
            "status": authorization.status,
            "asset_id": authorization.asset_id,
            "asset_name": authorization.asset_name,
            "terminal_id": authorization.terminal_id,
            "command": args.get("command"),
        }

    def _approval_consistency_error(self: Any, state: LoopState) -> str | None:
        snapshot = state.pending_approval_consistency
        if not snapshot:
            return None
        args = state.pending_tool_args or {}
        handler = self._tools.get("execute_command")
        terminal = getattr(handler, "_terminal", None)
        resolver = getattr(terminal, "resolve_terminal_authorization", None)
        belongs_to_asset = getattr(terminal, "session_belongs_to_asset", None)
        if resolver is None or belongs_to_asset is None:
            return "Missing terminal authorization resolver."
        try:
            authorization = resolver(state.context.runtime_id, str(snapshot["authorization_id"]))
        except ValueError as exc:
            return str(exc)
        checks = (
            (authorization.status == "active", "Terminal authorization is no longer active."),
            (authorization.terminal_id == snapshot["terminal_id"], "Authorized terminal changed after approval was requested."),
            (authorization.asset_id == snapshot["asset_id"], "Authorized asset changed after approval was requested."),
            (args.get("authorization_id") == snapshot["authorization_id"], "Approval target authorization changed."),
            (args.get("command") == snapshot["command"], "Approved command changed before execution."),
            (belongs_to_asset(authorization.terminal_id, authorization.asset_id), "Authorized terminal is no longer valid for the asset."),
        )
        return next((error for valid, error in checks if not valid), None)

    def _record_usage(
        self: Any,
        state: LoopState,
        usage: LLMTokenUsage | None,
        *,
        call_kind: str,
    ) -> None:
        if usage is None or self._usage_callback is None or usage.total_tokens <= 0:
            return
        self._usage_callback(state, usage, call_kind)

    def _prepare_tool_args(
        self: Any,
        handler: ToolHandler,
        args: dict[str, Any],
        state: LoopState,
    ) -> dict[str, Any]:
        metadata = self._get_tool_display_metadata(handler, args)
        requires_authorization = metadata.extra.get("kind") == "command" or metadata.extra.get("requiresAuthorization") is True
        if not requires_authorization:
            return args
        prepared = dict(args)
        if state.context.default_authorization_id and not str(prepared.get("authorization_id", "") or ""):
            prepared["authorization_id"] = state.context.default_authorization_id
        prepared.setdefault("asset_type", state.context.asset_type)
        prepared["runtime_id"] = state.context.runtime_id
        prepared["shell_type"] = state.context.shell_type
        prepared["execution_profile"] = state.context.execution_profile
        if state.context.device_vendor:
            prepared["device_vendor"] = state.context.device_vendor
        return prepared

    def _is_missing_command(self: Any, handler: ToolHandler, args: dict[str, Any]) -> bool:
        metadata = self._get_tool_display_metadata(handler, args)
        return (
            metadata.extra.get("kind") == "command"
            and handler.definition.name == "execute_command"
            and not str(args.get("command", "")).strip()
        )

    def _build_tool_call_payload(
        self: Any,
        *,
        handler: ToolHandler | None,
        tool_call_id: str | None,
        tool_name: str | None,
        args: dict[str, Any],
        command: str | None = None,
    ) -> dict[str, Any]:
        metadata = self._get_tool_display_metadata(handler, args)
        payload: dict[str, Any] = {
            "id": tool_call_id,
            "name": tool_name,
            "args": self._args_for_display(handler, args),
        }
        if metadata.description:
            payload["description"] = metadata.description
        if metadata.display_text:
            payload["displayText"] = metadata.display_text
        protected_keys = {"id", "name", "args", "command", "description", "displayText"}
        payload.update({key: value for key, value in metadata.extra.items() if key not in protected_keys})
        if metadata.extra.get("kind") == "command":
            execution_profile = str(args.get("execution_profile", "") or "").strip()
            device_vendor = str(args.get("device_vendor", "") or "").strip()
            if execution_profile:
                payload["executionProfile"] = execution_profile
            if device_vendor:
                payload["deviceVendor"] = device_vendor
        normalized_command = (command or "").strip()
        if normalized_command:
            payload["command"] = normalized_command
        return payload
