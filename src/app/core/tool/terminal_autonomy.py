from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from app.core.loop.loop_events import LoopEvent
from app.core.loop.loop_state import LoopState
from app.core.loop.message_manager import MessageManager
from app.core.loop.runtime_manager import LoopRuntimeManager
from app.core.tool.handler import ToolDisplayMetadata
from app.core.tool.schema import LLMToolDefinition
from app.db.repositories.assets import get_asset, list_assets
from app.db.session import Session, engine


def _json_tool_output(tool: str, status: str, payload: dict[str, Any] | None = None) -> str:
    return json.dumps({"tool": tool, "status": status, **(payload or {})}, ensure_ascii=False, separators=(",", ":"))


class ListAssetsHandler:
    @property
    def definition(self) -> LLMToolDefinition:
        return LLMToolDefinition(
            name="list_assets",
            description="List visible diagnostic assets with non-secret connection summaries. Only call this when remote asset discovery is required for the user's task.",
            input_schema={
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "enum": ["user_requested_assets", "remote_execution_required"],
                        "description": "Why asset discovery is needed. Use user_requested_assets when the user asked about assets/hosts; use remote_execution_required when the task cannot be completed in the current authorized terminal context.",
                    },
                    "justification": {
                        "type": "string",
                        "description": "A concise explanation grounded in the user's request or current task requirements.",
                    },
                },
                "required": ["intent", "justification"],
            },
        )

    def needs_approval(self, args: dict[str, Any]) -> tuple[str, str]:
        intent = str(args.get("intent") or "").strip()
        justification = str(args.get("justification") or "").strip()
        if intent not in {"user_requested_assets", "remote_execution_required"} or not justification:
            return "deny", "Asset discovery requires an explicit intent and justification."
        return "allow", "Listing assets only returns non-secret summaries."

    def display_metadata(self, args: dict[str, Any]) -> ToolDisplayMetadata:
        _ = args
        return ToolDisplayMetadata(
            description="List visible diagnostic assets.",
            display_text="List assets",
            extra={"kind": "asset_list"},
        )

    def execute(self, *, state: LoopState, step_id: str, args: dict[str, Any], manager: MessageManager | None = None) -> Iterator[LoopEvent]:
        _ = state, step_id, args
        with Session(engine) as session:
            assets = list_assets(session)
            result = {
                "assets": [
                    {
                        "asset_id": asset.id,
                        "name": asset.name,
                        "asset_type": asset.asset_type,
                        "group_id": asset.group_id,
                        "connection_status": "connectable",
                        "tags": [tag.strip() for tag in asset.tags.split(",") if tag.strip()],
                        "connectable": asset.id is not None,
                    }
                    for asset in assets
                    if asset.id is not None
                ]
            }
        output = _json_tool_output("list_assets", "ok", result)
        if manager:
            yield from manager.update(tool_output=output)
        return True, output


class RequestTerminalSessionHandler:
    def __init__(self, runtime_manager: LoopRuntimeManager) -> None:
        self._runtime_manager = runtime_manager

    @property
    def definition(self) -> LLMToolDefinition:
        return LLMToolDefinition(
            name="request_terminal_session",
            description="Request user approval to open a terminal session for a visible asset.",
            input_schema={
                "type": "object",
                "properties": {
                    "asset_id": {"type": "integer", "description": "Target asset ID."},
                    "reason": {"type": "string", "description": "Why this terminal session is needed."},
                    "intent": {
                        "type": "string",
                        "enum": ["user_requested_connection", "remote_execution_required"],
                        "description": "Why remote terminal access is needed. Use user_requested_connection when the user asked to connect to an asset; use remote_execution_required when the task cannot be completed in the current authorized terminal context.",
                    },
                },
                "required": ["asset_id", "reason", "intent"],
            },
        )

    def needs_approval(self, args: dict[str, Any]) -> tuple[str, str]:
        intent = str(args.get("intent") or "").strip()
        reason = str(args.get("reason") or "").strip()
        if intent not in {"user_requested_connection", "remote_execution_required"} or not reason:
            return "deny", "Remote terminal requests require an explicit intent and reason."
        return "allow", "Terminal session requests require separate user confirmation."

    def display_metadata(self, args: dict[str, Any]) -> ToolDisplayMetadata:
        asset_id = args.get("asset_id")
        return ToolDisplayMetadata(
            description="Request terminal access for an asset.",
            display_text=f"Request terminal access for asset {asset_id}",
            extra={"kind": "terminal_request"},
        )

    def execute(self, *, state: LoopState, step_id: str, args: dict[str, Any], manager: MessageManager | None = None) -> Iterator[LoopEvent]:
        _ = step_id
        try:
            asset_id = int(args.get("asset_id") or -1)
        except (TypeError, ValueError):
            output = _json_tool_output("request_terminal_session", "error", {"message": "A valid asset_id is required to request terminal access."})
            if manager:
                yield from manager.update(tool_output=output)
            return False, output
        reason = str(args.get("reason") or "").strip()
        if not reason:
            output = _json_tool_output("request_terminal_session", "error", {"message": "A reason is required to request terminal access."})
            if manager:
                yield from manager.update(tool_output=output)
            return False, output
        primary_asset_id = state.context.conversation_primary_asset_id if state.context.conversation_primary_asset_id is not None else state.context.asset_id
        is_cross_asset = asset_id != primary_asset_id
        if is_cross_asset and state.context.conversation_scope_mode != "multi":
            output = _json_tool_output(
                "request_terminal_session",
                "scope_denied",
                {
                    "assetId": asset_id,
                    "primaryAssetId": primary_asset_id,
                    "message": "This conversation is bound to one asset. Create a multi-asset task before requesting another asset.",
                },
            )
            if manager:
                yield from manager.update(tool_output=output)
            return False, output
        scope_expansion_required = asset_id not in state.context.allowed_asset_ids
        with Session(engine) as session:
            asset = get_asset(session, asset_id)
            if asset is None or asset.id is None:
                output = _json_tool_output("request_terminal_session", "error", {"assetId": asset_id, "message": "Asset is not visible or does not exist."})
                if manager:
                    yield from manager.update(tool_output=output)
                return False, output
            if self._runtime_manager.has_active_initial_authorization(state.context.runtime_id, asset.id):
                output = _json_tool_output(
                    "request_terminal_session",
                    "already_authorized",
                    {
                        "assetId": asset.id,
                        "assetName": asset.name,
                        "message": "The current terminal is already authorized for this asset. Use execute_command with the current authorization instead of requesting a new terminal session.",
                    },
                )
                if manager:
                    yield from manager.update(tool_output=output)
                return False, output
            request, _token, event = self._runtime_manager.create_terminal_request(
                state.context.runtime_id,
                conversation_id=state.context.conversation_id,
                asset_id=asset.id,
                asset_name=asset.name,
                reason=reason,
                scope_expansion_required=scope_expansion_required,
            )
            yield LoopEvent(
                event_type="terminal_session_request",
                runtime_id=state.context.runtime_id,
                phase=state.phase,
                payload=event,
            )
        output = _json_tool_output(
            "request_terminal_session",
            "pending_user_confirmation",
            {
                "requestId": request.request_id,
                "assetId": request.asset_id,
                "assetName": request.asset_name,
                "reason": request.reason,
                "scopeExpansionRequired": request.scope_expansion_required,
            },
        )
        if manager:
            yield from manager.update(tool_output=output)
        return True, output
