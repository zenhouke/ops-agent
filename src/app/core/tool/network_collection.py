from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any, Protocol

from app.core.connectors.device_profiles import NETWORK_CLI_PROFILE
from app.core.connectors.network_collection import NetworkCollectionKind, collection_commands
from app.core.loop.loop_events import LoopEvent
from app.core.loop.loop_state import LoopState
from app.core.loop.message_manager import MessageManager
from app.core.tool.handler import ToolDisplayMetadata
from app.core.tool.schema import LLMToolDefinition


class NetworkCollectionTerminal(Protocol):
    def get_session(self, terminal_id: str) -> Any | None: ...
    def resolve_terminal_authorization(self, runtime_id: str, authorization_id: str) -> Any: ...
    def session_belongs_to_asset(self, terminal_id: str, asset_id: int) -> bool: ...
    def append_terminal_command_submitted(
        self,
        runtime_id: str,
        *,
        authorization_id: str,
        asset_id: int,
        asset_name: str,
        terminal_id: str,
        command: str,
        approval_policy: str,
    ) -> dict[str, Any]: ...
    def acquire_terminal_slot(self, runtime_id: str, terminal_id: str) -> bool: ...
    def release_terminal_slot(self, runtime_id: str, terminal_id: str) -> None: ...


_TOOL_NAMES: dict[NetworkCollectionKind, str] = {
    "facts": "get_network_device_facts",
    "interfaces": "get_network_interfaces",
    "neighbors": "get_network_l2_neighbors",
}

_DISPLAY_NAMES: dict[NetworkCollectionKind, str] = {
    "facts": "Collect network device facts",
    "interfaces": "Collect network interfaces",
    "neighbors": "Collect L2 neighbors",
}


class NetworkCollectionHandler:
    def __init__(self, terminal: NetworkCollectionTerminal, kind: NetworkCollectionKind) -> None:
        self._terminal = terminal
        self._kind: NetworkCollectionKind = kind

    @property
    def definition(self) -> LLMToolDefinition:
        return LLMToolDefinition(
            name=_TOOL_NAMES[self._kind],
            description=(
                f"Read and normalize network device {self._kind} using vendor-controlled read-only commands. "
                "Requires an active terminal authorization for the target asset. Never changes device configuration."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "authorization_id": {
                        "type": "string",
                        "description": "Active runtime terminal authorization ID for the target network asset.",
                    },
                },
                "required": ["authorization_id"],
                "additionalProperties": False,
            },
        )

    def needs_approval(self, args: dict[str, Any]) -> tuple[str, str]:
        authorization_id = str(args.get("authorization_id", "") or "")
        runtime_id = str(args.get("runtime_id", "") or "")
        if not authorization_id or not runtime_id:
            return "deny", "Structured network collection requires an active terminal authorization."
        try:
            authorization = self._terminal.resolve_terminal_authorization(runtime_id, authorization_id)
        except ValueError as exc:
            return "deny", str(exc)
        if authorization.execution_profile != NETWORK_CLI_PROFILE:
            return "deny", "Structured network collection is only available for network device assets."
        if not self._terminal.session_belongs_to_asset(authorization.terminal_id, authorization.asset_id):
            return "deny", "Authorized terminal no longer belongs to the expected asset."
        args.update({
            "asset_id": authorization.asset_id,
            "asset_name": authorization.asset_name,
            "terminal_id": authorization.terminal_id,
            "asset_type": authorization.asset_type,
            "execution_profile": authorization.execution_profile,
            "device_vendor": authorization.device_vendor,
        })
        vendor = str(authorization.device_vendor or "generic")
        if vendor != "generic":
            try:
                collection_commands(vendor, self._kind)
            except ValueError as exc:
                return "deny", str(exc)
        return "allow", "Vendor-controlled read-only network collection."

    def display_metadata(self, args: dict[str, Any]) -> ToolDisplayMetadata:
        return ToolDisplayMetadata(
            description=f"Read-only normalized network {self._kind} collection.",
            display_text=_DISPLAY_NAMES[self._kind],
            extra={
                "kind": "network_collection",
                "requiresAuthorization": True,
                "collectionKind": self._kind,
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
        _ = step_id
        terminal_id = str(args.get("terminal_id", "") or "")
        authorization_id = str(args.get("authorization_id", "") or "")
        session_manager = self._terminal.get_session(terminal_id)
        if session_manager is None:
            return False, "Authorized terminal session does not exist."
        if not self._terminal.acquire_terminal_slot(state.context.runtime_id, terminal_id):
            return False, "The authorized terminal is currently busy."
        try:
            plan = session_manager.plan_network_collection(self._kind)
            for spec in plan["commands"]:
                self._terminal.append_terminal_command_submitted(
                    state.context.runtime_id,
                    authorization_id=authorization_id,
                    asset_id=int(args["asset_id"]),
                    asset_name=str(args.get("asset_name", "")),
                    terminal_id=terminal_id,
                    command=str(spec["command"]),
                    approval_policy="allow_read_only_collection",
                )
            result = session_manager.collect_network(self._kind, read_timeout=30.0)
            output = json.dumps(
                {"tool": _TOOL_NAMES[self._kind], "status": "ok", **result},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            if manager:
                yield from manager.update(tool_output=output)
            return True, output
        except Exception as exc:
            return False, f"Structured network collection failed: {exc}"
        finally:
            self._terminal.release_terminal_slot(state.context.runtime_id, terminal_id)


def build_network_collection_handlers(terminal: NetworkCollectionTerminal) -> list[NetworkCollectionHandler]:
    return [NetworkCollectionHandler(terminal, kind) for kind in ("facts", "interfaces", "neighbors")]
