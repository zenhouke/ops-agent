from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Iterator
from typing import Any, Protocol

logger = logging.getLogger(__name__)

DEFAULT_COMMAND_TIMEOUT_SECONDS = 60.0

from app.core.loop.loop_events import (
    LoopEvent,
    emit_failed,
)
from app.core.loop.loop_state import LoopState
from app.core.loop.message_manager import MessageManager
from app.core.tool.handler import ToolDisplayMetadata
from app.core.tool.schema import LLMToolDefinition
from app.core.approval import ApprovalContext
from app.core.connectors.execution import ExecutionContext
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

    def execute_interactive_command(
        self,
        terminal_id: str,
        command: str,
        *,
        context: ExecutionContext | None = None,
        on_output_chunk: Any | None = None,
        on_command_event: Any | None = None,
    ) -> Any: ...


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
                    "terminal_id": {
                        "type": "string",
                        "description": "Target terminal session ID. Must match the terminal bound to authorization_id.",
                    },
                    "command": {"type": "string", "description": "The command to execute, must be specified."},
                    "working_directory": {"type": "string", "description": "Working directory (optional)"},
                },
                "required": ["authorization_id", "terminal_id", "command"],
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
            requested_terminal_id = str(args.get("terminal_id", "") or "")
            if not requested_terminal_id:
                return "deny", "Missing terminal_id for terminal authorization."
            if requested_terminal_id and requested_terminal_id != authorization.terminal_id:
                return "deny", "terminal_id does not match the terminal authorization."
            if not self._terminal.session_belongs_to_asset(authorization.terminal_id, authorization.asset_id):
                return "deny", "Authorized terminal is no longer valid for the asset."
            if self._terminal.get_session(authorization.terminal_id) is None:
                return "deny", "Terminal session does not exist, cannot request command approval."
            args["asset_id"] = authorization.asset_id
            args["asset_name"] = authorization.asset_name
            args["terminal_id"] = authorization.terminal_id
            args["asset_type"] = authorization.asset_type
            args["shell_type"] = authorization.shell_type
            args["execution_profile"] = authorization.execution_profile
            if authorization.device_vendor:
                args["device_vendor"] = authorization.device_vendor
        context = ApprovalContext(
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
        terminal_id = authorization.terminal_id
        requested_terminal_id = str(args.get("terminal_id", "") or "")
        if not requested_terminal_id:
            error = "Missing terminal_id for terminal authorization."
            if manager:
                yield from manager.update(text=f"\nError: {error}")
            return False, error
        if requested_terminal_id and requested_terminal_id != terminal_id:
            error = "terminal_id does not match the terminal authorization."
            if manager:
                yield from manager.update(text=f"\nError: {error}")
            return False, error
        args["asset_id"] = authorization.asset_id
        args["asset_name"] = authorization.asset_name
        args["terminal_id"] = authorization.terminal_id
        args["asset_type"] = authorization.asset_type
        args["shell_type"] = authorization.shell_type
        args["execution_profile"] = authorization.execution_profile
        if authorization.device_vendor:
            args["device_vendor"] = authorization.device_vendor
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

        release_slot_in_finally = True

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
            execution_context = ExecutionContext(
                working_directory=step.working_directory,
                timeout_seconds=DEFAULT_COMMAND_TIMEOUT_SECONDS,
                cancel_check=lambda: state.cancel_requested,
            )
            if authorization.execution_profile == "posix-shell":
                execution_queue: queue.Queue[tuple[str, Any]] = queue.Queue()

                def on_output_chunk(chunk: str) -> None:
                    execution_queue.put(("chunk", chunk))

                def on_command_event(event: dict[str, Any]) -> None:
                    execution_queue.put(("command_event", event))

                def run_interactive_execution() -> None:
                    try:
                        result = self._terminal.execute_interactive_command(
                            terminal_id,
                            command,
                            context=execution_context,
                            on_output_chunk=on_output_chunk,
                            on_command_event=on_command_event,
                        )
                        execution_queue.put(("result", result))
                    except Exception as exc:
                        execution_queue.put(("error", exc))

                worker = threading.Thread(target=run_interactive_execution, daemon=True)
                worker.start()
                execution = None
                streamed_output = ""
                while True:
                    if state.cancel_requested and not worker.is_alive():
                        break
                    try:
                        event_type, payload = execution_queue.get(timeout=0.2)
                    except queue.Empty:
                        if state.cancel_requested and not worker.is_alive():
                            break
                        continue
                    if event_type == "chunk":
                        chunk_text = str(payload)
                        streamed_output += chunk_text
                        if chunk_text and manager:
                            yield from manager.update(tool_output=chunk_text)
                        continue
                    if event_type == "command_event":
                        event_payload = dict(payload)
                        event_kind = str(event_payload.get("kind") or "terminal_status")
                        yield LoopEvent(
                            event_type=event_kind,  # type: ignore[arg-type]
                            runtime_id=ctx.runtime_id,
                            phase=state.phase,
                            payload={**event_payload, "runtimeId": ctx.runtime_id, "stepId": step.step_id},
                            step_id=step.step_id,
                        )
                        continue
                    if event_type == "error":
                        raise payload
                    execution = payload
                    break
                worker.join(timeout=1.0)
                if execution is None:
                    return False, "Command execution cancelled."
            else:
                if state.cancel_requested:
                    return False, "Command execution cancelled."
                execution_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
                execution_id_holder: dict[str, str] = {}
                cancel_requested_for_execution = False

                def run_sync_execution() -> None:
                    try:
                        execution_id = session_manager.start_execution(command, execution_context)
                        execution_id_holder["execution_id"] = execution_id
                        if state.cancel_requested:
                            try:
                                session_manager.cancel_execution(execution_id)
                            except Exception:
                                logger.exception(
                                    "Command cancellation failed runtime_id=%s, command_id=%s",
                                    ctx.runtime_id,
                                    step.step_id,
                                )
                        result = session_manager.get_execution_result(execution_id)
                        execution_queue.put(("result", result))
                    except Exception as exc:
                        execution_queue.put(("error", exc))

                worker = threading.Thread(target=run_sync_execution, daemon=True)
                worker.start()
                execution = None
                streamed_output = ""
                while True:
                    try:
                        event_type, payload = execution_queue.get(timeout=0.2)
                    except queue.Empty:
                        if state.cancel_requested and worker.is_alive():
                            execution_id = execution_id_holder.get("execution_id")
                            if execution_id and not cancel_requested_for_execution:
                                cancel_requested_for_execution = True
                                try:
                                    session_manager.cancel_execution(execution_id)
                                except Exception:
                                    logger.exception(
                                        "Command cancellation failed runtime_id=%s, command_id=%s",
                                        ctx.runtime_id,
                                        step.step_id,
                                    )
                            release_slot_in_finally = False

                            def release_slot_after_worker() -> None:
                                try:
                                    worker.join()
                                finally:
                                    try:
                                        self._terminal.release_terminal_slot(ctx.runtime_id, terminal_id)
                                    except Exception:
                                        logger.exception(
                                            "Deferred terminal slot release failed runtime_id=%s terminal_id=%s",
                                            ctx.runtime_id,
                                            terminal_id,
                                        )

                            threading.Thread(target=release_slot_after_worker, daemon=True).start()
                            return False, "Command execution cancelled."
                        continue
                    if event_type == "error":
                        raise payload
                    execution = payload
                    break
                if state.cancel_requested:
                    return False, "Command execution cancelled."

            step.output = execution.output
            step.exit_code = execution.exit_code
            state.last_output_excerpt = execution.output[-4000:] if execution.output else ""

            remaining_output = execution.output[len(streamed_output) :] if execution.output.startswith(streamed_output) else execution.output
            if remaining_output and manager:
                yield from manager.update(tool_output=remaining_output)

            success = execution.success and not execution.needs_attention
            return success, execution.output
        except Exception as exc:
            logger.exception("Command execution exception runtime_id=%s, command_id=%s", ctx.runtime_id, step.step_id)
            error = f"Command execution exception: {exc}"
            if manager:
                yield from manager.update(text=f"\nError: {error}")
            return False, error
        finally:
            if release_slot_in_finally:
                self._terminal.release_terminal_slot(ctx.runtime_id, terminal_id)
