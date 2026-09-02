from __future__ import annotations

import logging
import uuid
import json
from collections.abc import Iterator
from typing import Any, Protocol

logger = logging.getLogger(__name__)

DEFAULT_COMMAND_TIMEOUT_SECONDS = 15.0

from app.core.loop.loop_events import (
    LoopEvent,
    emit_failed,
)
from app.core.loop.loop_state import LoopState
from app.core.loop.message_manager import MessageManager
from app.core.tool.handler import ToolDisplayMetadata
from app.core.tool.schema import LLMToolDefinition
from app.core.approval import ApprovalContext, is_multiline_network_command
from app.core.connectors.device_profiles import NETWORK_CLI_PROFILE
from app.core.connectors.execution import ExecutionContext
from app.db.session import Session, engine
from app.db.repositories.audit import create_audit_log
from app.services.redaction_service import RedactionService
from app.services.approval_service import get_approval_service


class TerminalSessionResolver(Protocol):
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


class ExecuteCommandHandler:
    def __init__(self, terminal: TerminalSessionResolver) -> None:
        self._terminal = terminal

    @property
    def definition(self) -> LLMToolDefinition:
        return LLMToolDefinition(
            name="execute_command",
            description="Execute terminal command. The system will automatically determine whether to allow, reject, or require user approval based on the approval policy in settings.json.",
            input_schema={
                "type": "object",
                "properties": {
                    "authorization_id": {
                        "type": "string",
                        "description": "Runtime terminal authorization ID for the target terminal session.",
                    },
                    "command": {"type": "string", "description": "The command to execute, must be specified."},
                    "working_directory": {"type": "string", "description": "Working directory (optional)"},
                },
                "required": ["authorization_id", "command"],
            },
        )

    def needs_approval(self, args: dict[str, Any]) -> tuple[str, str]:
        command = str(args.get("command", "")).strip()
        authorization_id = str(args.get("authorization_id", "") or "")
        if not authorization_id:
            return "deny", "Missing terminal authorization."
        runtime_id = str(args.get("runtime_id", "") or "")
        if runtime_id:
            try:
                authorization = self._terminal.resolve_terminal_authorization(runtime_id, authorization_id)
            except ValueError as exc:
                return "deny", str(exc)
            args["conversation_id"] = authorization.conversation_id
            args["asset_id"] = authorization.asset_id
            args["asset_name"] = authorization.asset_name
            args["terminal_id"] = authorization.terminal_id
            args["asset_type"] = authorization.asset_type
            args["shell_type"] = authorization.shell_type
            args["execution_profile"] = authorization.execution_profile
            if authorization.device_vendor:
                args["device_vendor"] = authorization.device_vendor
        context = ApprovalContext(
            conversation_id=str(args.get("conversation_id", "") or ""),
            asset_id=int(args["asset_id"]) if args.get("asset_id") is not None else None,
            asset_type=str(args.get("asset_type", "") or ""),
            shell_type=str(args.get("shell_type", "") or ""),
            profile=str(args.get("execution_profile", "posix-shell") or "posix-shell"),
            vendor=str(args.get("device_vendor", "") or "") or None,
        )
        action, reason = get_approval_service().check_command(command, context)
        return action, reason

    def display_metadata(self, args: dict[str, Any]) -> ToolDisplayMetadata:
        command = str(args.get("command", "")).strip()
        return ToolDisplayMetadata(
            description="Execute terminal command.",
            display_text=command or "Execute terminal command",
            extra={"kind": "command"},
        )

    @staticmethod
    def _scope_error(state: LoopState, asset_id: int) -> str | None:
        ctx = state.context
        primary_asset_id = (
            ctx.conversation_primary_asset_id
            if ctx.conversation_primary_asset_id is not None
            else ctx.asset_id
        )
        if asset_id not in ctx.allowed_asset_ids:
            return "Authorized asset is outside the current conversation allowlist."
        if ctx.conversation_scope_mode == "single" and asset_id != primary_asset_id:
            return "A single-asset conversation cannot execute commands on another asset."
        return None

    def execute(self, *, state: LoopState, step_id: str, args: dict[str, Any], manager: MessageManager | None = None) -> Iterator[LoopEvent]:
        ctx = state.context
        authorization_id = str(args.get("authorization_id", "") or "")
        command = str(args.get("command", "")).strip()
        if not authorization_id:
            error = "Missing terminal authorization."
            if manager:
                yield from manager.update(text=f"\nError: {error}")
            return False, error
        try:
            authorization = self._terminal.resolve_terminal_authorization(ctx.runtime_id, authorization_id)
        except ValueError as exc:
            error = str(exc)
            if manager:
                yield from manager.update(text=f"\nError: {error}")
            return False, error
        scope_error = self._scope_error(state, authorization.asset_id)
        if scope_error:
            if manager:
                yield from manager.update(text=f"\nError: {scope_error}")
            return False, scope_error
        terminal_id = authorization.terminal_id
        args["asset_id"] = authorization.asset_id
        args["asset_name"] = authorization.asset_name
        args["terminal_id"] = authorization.terminal_id
        args["asset_type"] = authorization.asset_type
        args["shell_type"] = authorization.shell_type
        args["execution_profile"] = authorization.execution_profile
        if authorization.device_vendor:
            args["device_vendor"] = authorization.device_vendor
        if authorization.execution_profile == NETWORK_CLI_PROFILE and is_multiline_network_command(command):
            error = "Network device commands must be submitted one line at a time for per-command approval."
            if manager:
                yield from manager.update(text=f"\nError: {error}")
            return False, error
        if not self._terminal.session_belongs_to_asset(terminal_id, authorization.asset_id):
            error = "Authorized terminal no longer belongs to the expected asset."
            if manager:
                yield from manager.update(text=f"\nError: {error}")
            return False, error

        step = state.get_step(step_id)
        if step is None:
            return False, "Step not found"

        session_manager = self._terminal.get_session(terminal_id)
        if session_manager is None:
            error = "Terminal session does not exist, cannot execute command."
            if manager:
                yield from manager.update(text=f"\nError: {error}")
            return False, error

        if not self._terminal.acquire_terminal_slot(ctx.runtime_id, terminal_id):
            error = "currently executing command, please wait for it to finish"
            if manager:
                yield from manager.update(text=f"\nError: {error}")
            return False, error

        try:
            self._terminal.append_terminal_command_submitted(
                ctx.runtime_id,
                authorization_id=authorization.authorization_id,
                asset_id=authorization.asset_id,
                asset_name=authorization.asset_name,
                terminal_id=authorization.terminal_id,
                command=command,
                approval_policy=str(args.get("approval_policy", "allow")),
            )
            with Session(engine) as audit_session:
                create_audit_log(
                    audit_session,
                    action="command.submitted",
                    entity_type="runtime",
                    actor="agent-with-operator-policy",
                    asset_id=authorization.asset_id,
                    conversation_id=ctx.conversation_id,
                    details=json.dumps(
                        {
                            "runtimeId": ctx.runtime_id,
                            "terminalId": terminal_id,
                            "approvalPolicy": str(args.get("approval_policy", "allow")),
                            "command": RedactionService().redact_text(command),
                        },
                        ensure_ascii=False,
                    ),
                )
            execution_id = str(uuid.uuid4())
            state.active_terminal_id = terminal_id
            state.active_execution_id = execution_id
            session_manager.start_execution(
                command,
                ExecutionContext(working_directory=step.working_directory, timeout_seconds=DEFAULT_COMMAND_TIMEOUT_SECONDS),
                execution_id=execution_id,
            )
            execution = session_manager.get_execution_result(execution_id)
            
            step.output = execution.output
            step.exit_code = execution.exit_code
            state.last_output_excerpt = execution.output[-4000:] if execution.output else ""

            if execution.output and manager:
                yield from manager.update(tool_output=execution.output)

            success = execution.success and not execution.needs_attention
            return success, execution.output
        except Exception as exc:
            logger.exception("Command execution exception runtime_id=%s, command_id=%s", ctx.runtime_id, step.step_id)
            error = f"Command execution exception: {exc}"
            if manager:
                yield from manager.update(text=f"\nError: {error}")
            return False, error
        finally:
            state.active_terminal_id = None
            state.active_execution_id = None
            self._terminal.release_terminal_slot(ctx.runtime_id, terminal_id)
