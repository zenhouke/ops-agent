from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import json
import re
import logging
import threading
import time
from typing import Any, Awaitable, Callable, TypeVar, cast

import anyio
from starlette.websockets import WebSocketDisconnect

from app.core.connectors.context_bridge import build_terminal_context
from app.core.connectors.execution import ExecutionContext, ExecutionResult
from app.core.connectors.session_manager import TerminalSessionManager
from app.core.connectors.ssh_proxy import describe_ssh_proxy_error


T = TypeVar("T")
RunSyncCallable = Callable[..., Awaitable[T]]
run_sync = cast(RunSyncCallable[Any], getattr(anyio.to_thread, "run_sync"))


import uuid


ANSI_PATTERN = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
EXIT_STATUS_PATTERN = re.compile(r"__OPS_AGENT_EXIT_STATUS_([A-Za-z0-9_]+)__:(-?\d+)")
logger = logging.getLogger(__name__)


@dataclass
class TerminalSessionRuntime:
    session_manager: TerminalSessionManager
    state: str = "created"
    connection_ids: set[str] = field(default_factory=set)
    last_detached_at: datetime | None = None
    reader_stop: threading.Event = field(default_factory=threading.Event)
    reader_thread: threading.Thread | None = None
    writer_connection_id: str | None = None
    buffer_lock: threading.RLock = field(default_factory=threading.RLock)


class TerminalService:
    SESSION_TTL = timedelta(minutes=15)
    MAX_OUTPUT_BUFFER_CHARS = 256 * 1024
    TERMINAL_READER_IDLE_SECONDS = 0.01
    WEBSOCKET_TAIL_IDLE_SECONDS = 0.016
    COMMAND_POLL_SECONDS = 0.02
    COMMAND_STARTUP_IDLE_SECONDS = 0.2

    def __init__(self, connector_factory, persistence=None):
        self._connector_factory = connector_factory
        self._sessions: dict[str, TerminalSessionRuntime] = {}
        self._session_keys: dict[str, str] = {}
        self._output_buffers: dict[str, deque[tuple[int, str]]] = {}
        self._output_buffer_sizes: dict[str, int] = {}
        self._output_sequences: dict[str, int] = {}
        self._command_event_buffers: dict[str, deque[tuple[int, dict[str, Any]]]] = {}
        self._command_event_sequences: dict[str, int] = {}
        self._registry_lock = threading.RLock()

    def _expire_detached_sessions(self) -> None:
        now = datetime.now(UTC)
        expired_ids: list[str] = []
        with self._registry_lock:
            for terminal_id, runtime in list(self._sessions.items()):
                if runtime.state != "detached" or runtime.last_detached_at is None:
                    continue
                if now - runtime.last_detached_at >= self.SESSION_TTL:
                    expired_ids.append(terminal_id)
        for terminal_id in expired_ids:
            self.close_session(terminal_id)

    def open_session(self, asset, *, reuse_existing: bool = False):
        self._expire_detached_sessions()
        session_key = self._build_session_key(asset)
        if reuse_existing:
            terminal_id = self.find_session_id(session_key)
            if terminal_id is not None:
                return {"terminal_id": terminal_id, "channel": "terminal connected", "error": ""}
        terminal_id = str(uuid.uuid4())
        connector = None
        session_manager = None
        try:
            connector = self._connector_factory(asset)
            session_manager = TerminalSessionManager(connector)
            session_manager.open()
        except Exception as exc:
            if session_manager is not None and session_manager.is_open:
                session_manager.close()
            elif connector is not None:
                connector.close()
            return {"terminal_id": None, "channel": None, "error": describe_ssh_proxy_error(exc)}
        duplicate_session_manager = None
        with self._registry_lock:
            if reuse_existing:
                existing_terminal_id = self.find_session_id(session_key)
                if existing_terminal_id is not None:
                    duplicate_session_manager = session_manager
                    terminal_id = existing_terminal_id
                else:
                    self._sessions[terminal_id] = TerminalSessionRuntime(session_manager=session_manager, state="created")
                    self._session_keys[terminal_id] = session_key
                    self._output_buffers[terminal_id] = deque(maxlen=4000)
                    self._output_buffer_sizes[terminal_id] = 0
                    self._output_sequences[terminal_id] = 0
                    self._command_event_buffers[terminal_id] = deque(maxlen=8000)
                    self._command_event_sequences[terminal_id] = 0
            else:
                self._sessions[terminal_id] = TerminalSessionRuntime(session_manager=session_manager, state="created")
                self._session_keys[terminal_id] = session_key
                self._output_buffers[terminal_id] = deque(maxlen=4000)
                self._output_buffer_sizes[terminal_id] = 0
                self._output_sequences[terminal_id] = 0
                self._command_event_buffers[terminal_id] = deque(maxlen=8000)
                self._command_event_sequences[terminal_id] = 0
        if duplicate_session_manager is not None:
            duplicate_session_manager.close()
            return {"terminal_id": terminal_id, "channel": "terminal connected", "error": ""}
        self._start_session_reader(terminal_id)
        return {"terminal_id": terminal_id, "channel": "terminal connected", "error": ""}

    def _start_session_reader(self, terminal_id: str) -> None:
        runtime = self._sessions.get(terminal_id)
        if runtime is None or runtime.reader_thread is not None:
            return

        thread = threading.Thread(
            target=self._session_reader_loop,
            args=(terminal_id, runtime),
            name=f"ops-terminal-reader-{terminal_id[:8]}",
            daemon=True,
        )
        runtime.reader_thread = thread
        thread.start()

    def _session_reader_loop(self, terminal_id: str, runtime: TerminalSessionRuntime) -> None:
        while not runtime.reader_stop.is_set():
            if terminal_id not in self._sessions:
                return
            try:
                output = runtime.session_manager.read()
            except Exception as exc:
                logger.warning("Terminal reader failed terminal_id=%s: %s", terminal_id, exc)
                return
            if output:
                self._append_output(terminal_id, output)
            else:
                time.sleep(self.TERMINAL_READER_IDLE_SECONDS)

    async def stream_session(self, terminal_id: str, websocket) -> None:
        self._expire_detached_sessions()
        runtime = self._sessions.get(terminal_id)
        if runtime is None:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        connection_id = str(uuid.uuid4())
        runtime.connection_ids.add(connection_id)
        runtime.state = "attached"
        runtime.last_detached_at = None
        runtime.writer_connection_id = connection_id
        await websocket.send_json({"type": "connection_state", "writable": True})

        buffered_output = self.read_buffered_output(terminal_id)
        if buffered_output:
            await websocket.send_json({"type": "output", "data": buffered_output})
        output_cursor = self.get_output_cursor(terminal_id)

        closed = anyio.Event()
        send_lock = anyio.Lock()
        try:
            async with anyio.create_task_group() as task_group:
                task_group.start_soon(self._receive_websocket_input, terminal_id, runtime, connection_id, websocket, closed, send_lock)
                task_group.start_soon(self._tail_terminal_output, terminal_id, output_cursor, websocket, closed, send_lock)
        except (WebSocketDisconnect, RuntimeError):
            pass
        except Exception as exc:
            logger.exception("TaskGroup failed for terminal_id=%s: %s", terminal_id, str(exc))
            try:
                await websocket.send_json({"type": "error", "message": f"Terminal session error: {str(exc)}"})
            except Exception:
                pass
        finally:
            runtime.connection_ids.discard(connection_id)
            if runtime.writer_connection_id == connection_id:
                runtime.writer_connection_id = None
            if not runtime.connection_ids and terminal_id in self._sessions:
                runtime.state = "detached"
                runtime.last_detached_at = datetime.now(UTC)

    async def _send_readonly_connection_error(self, websocket, send_lock) -> None:
        try:
            async with send_lock:
                await websocket.send_json({"type": "error", "message": "terminal connection is read-only"})
        except (WebSocketDisconnect, RuntimeError):
            pass

    async def _receive_websocket_input(self, terminal_id: str, runtime: TerminalSessionRuntime, connection_id: str, websocket, closed, send_lock) -> None:
        try:
            while True:
                message = await websocket.receive_json()
                message_type = message.get("type")
                if message_type == "input":
                    if runtime.writer_connection_id != connection_id:
                        await self._send_readonly_connection_error(websocket, send_lock)
                        continue
                    await run_sync(runtime.session_manager.write, message.get("data", ""))
                elif message_type == "resize":
                    if runtime.writer_connection_id != connection_id:
                        await self._send_readonly_connection_error(websocket, send_lock)
                        continue
                    try:
                        cols = int(message.get("cols", 80))
                        rows = int(message.get("rows", 24))
                    except (TypeError, ValueError):
                        try:
                            async with send_lock:
                                await websocket.send_json({"type": "error", "message": "invalid terminal size"})
                        except (WebSocketDisconnect, RuntimeError):
                            pass
                        continue
                    if cols < 1 or cols > 500 or rows < 1 or rows > 200:
                        try:
                            async with send_lock:
                                await websocket.send_json({"type": "error", "message": "invalid terminal size"})
                        except (WebSocketDisconnect, RuntimeError):
                            pass
                        continue
                    try:
                        await run_sync(runtime.session_manager.resize, cols, rows)
                    except Exception as exc:
                        logger.warning("Terminal resize failed terminal_id=%s cols=%s rows=%s: %s", terminal_id, cols, rows, exc)
                elif message_type == "ping":
                    try:
                        async with send_lock:
                            await websocket.send_json({"type": "pong"})
                    except (WebSocketDisconnect, RuntimeError):
                        pass
        except (WebSocketDisconnect, RuntimeError):
            return
        finally:
            closed.set()

    async def _tail_terminal_output(self, terminal_id: str, cursor: int, websocket, closed, send_lock) -> None:
        while True:
            cursor, output = self.read_output_since(terminal_id, cursor)
            if output:
                try:
                    async with send_lock:
                        await websocket.send_json({"type": "output", "data": output})
                except (WebSocketDisconnect, RuntimeError):
                    closed.set()
                    return
            if closed.is_set():
                return
            await anyio.sleep(self.WEBSOCKET_TAIL_IDLE_SECONDS)

    def close_session(self, terminal_id: str) -> bool:
        with self._registry_lock:
            runtime = self._sessions.pop(terminal_id, None)
            if runtime is None:
                return False
            self._session_keys.pop(terminal_id, None)
            self._output_buffers.pop(terminal_id, None)
            self._output_buffer_sizes.pop(terminal_id, None)
            self._output_sequences.pop(terminal_id, None)
            self._command_event_buffers.pop(terminal_id, None)
            self._command_event_sequences.pop(terminal_id, None)
        runtime.writer_connection_id = None
        runtime.reader_stop.set()
        reader_thread = runtime.reader_thread
        runtime.session_manager.close()
        if reader_thread is not None and reader_thread is not threading.current_thread():
            reader_thread.join(timeout=1.0)
        return True

    def get_session(self, terminal_id: str):
        runtime = self._sessions.get(terminal_id)
        return runtime.session_manager if runtime is not None else None

    def find_session_id(self, session_key: str) -> str | None:
        with self._registry_lock:
            for terminal_id, current_key in self._session_keys.items():
                if current_key == session_key and terminal_id in self._sessions:
                    return terminal_id
        return None

    def session_belongs_to_asset(self, terminal_id: str, asset_id: int) -> bool:
        with self._registry_lock:
            return self._session_keys.get(terminal_id) == f"asset:{asset_id}" and terminal_id in self._sessions

    def send_input(self, terminal_id: str, data: str) -> str | None:
        runtime = self._sessions.get(terminal_id)
        if runtime is None:
            raise ValueError("terminal session not found")
        normalized = data if data.endswith(("\n", "\r")) else f"{data}\r"
        runtime.session_manager.write(normalized)
        return None

    def execute_interactive_command(
        self,
        terminal_id: str,
        command: str,
        *,
        context: ExecutionContext | None = None,
        on_output_chunk: Callable[[str], None] | None = None,
        on_command_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> ExecutionResult:
        runtime = self._sessions.get(terminal_id)
        if runtime is None:
            raise ValueError("terminal session not found")

        timeout_seconds = (
            context.timeout_seconds
            if context is not None and context.timeout_seconds is not None and context.timeout_seconds > 0
            else 15.0
        )
        command_id = str(uuid.uuid4())
        exit_marker_id = command_id.replace("-", "_")
        shell_kind = runtime.session_manager.shell_kind()
        self._wait_for_output_idle(terminal_id)
        prompt_before = self._last_prompt_text(self.read_buffered_output(terminal_id), shell_kind)

        start_event = {
            "id": f"command-start-{command_id}",
            "kind": "command_start",
            "commandId": command_id,
            "terminalId": terminal_id,
            "command": command,
        }
        self._append_command_event(terminal_id, start_event)
        if on_command_event is not None:
            on_command_event(start_event)

        output_cursor = self.get_output_cursor(terminal_id)
        wrapped_command = self._command_with_exit_status_marker(command, shell_kind, exit_marker_id)
        self.send_input(terminal_id, wrapped_command)

        deadline = time.monotonic() + timeout_seconds
        captured_parts: list[str] = []
        streamed_output = ""
        cancel_requested = context.cancel_check if context is not None else None

        def emit_command_chunk(chunk: str) -> None:
            if not chunk:
                return
            chunk_event = {
                "id": f"command-chunk-{command_id}-{uuid.uuid4()}",
                "kind": "command_chunk",
                "commandId": command_id,
                "terminalId": terminal_id,
                "stream": "stdout",
                "text": chunk,
            }
            self._append_command_event(terminal_id, chunk_event)
            if on_command_event is not None:
                on_command_event(chunk_event)
            if on_output_chunk is not None:
                try:
                    on_output_chunk(chunk)
                except Exception:
                    logger.exception("Command output callback failed terminal_id=%s command_id=%s", terminal_id, command_id)

        completed = False
        stopped = False
        while time.monotonic() < deadline:
            if cancel_requested is not None and cancel_requested():
                stopped = True
                try:
                    self.send_input(terminal_id, "\x03")
                except Exception:
                    logger.warning("Failed to send interrupt to terminal_id=%s command_id=%s", terminal_id, command_id, exc_info=True)
                break
            output_cursor, output = self.read_output_since(terminal_id, output_cursor)
            if output:
                captured_parts.append(output)
                raw_so_far = "".join(captured_parts)
                extracted_so_far = self._extract_natural_command_output(raw_so_far, command, shell_kind)
                if len(extracted_so_far) > len(streamed_output):
                    chunk = extracted_so_far[len(streamed_output) :]
                    streamed_output = extracted_so_far
                    emit_command_chunk(chunk)
                if self._looks_like_prompt(raw_so_far, shell_kind, prompt_before):
                    completed = True
                    break
            time.sleep(self.COMMAND_POLL_SECONDS)

        raw_output = "".join(captured_parts)
        exit_code = self._extract_exit_status(raw_output, exit_marker_id)
        output = self._extract_natural_command_output(raw_output, command, shell_kind)
        if len(output) > len(streamed_output):
            emit_command_chunk(output[len(streamed_output) :])
            streamed_output = output
        success = completed and exit_code == 0
        end_event = {
            "id": f"command-end-{command_id}",
            "kind": "command_end",
            "commandId": command_id,
            "terminalId": terminal_id,
            "exitCode": exit_code if completed else None,
            "completionReason": "manual_stop" if stopped else ("prompt_detected" if completed else "timeout"),
        }
        self._append_command_event(terminal_id, end_event)
        if on_command_event is not None:
            on_command_event(end_event)

        return ExecutionResult(
            execution_id=command_id,
            output=output,
            completed=completed,
            success=success,
            needs_attention=not success,
            exit_code=exit_code if completed else None,
            completion_reason="manual_stop" if stopped else ("prompt_detected" if completed else "timeout"),
            prompt_before=prompt_before,
            prompt_after=self._last_prompt_text(raw_output, shell_kind),
        )

    def _command_with_exit_status_marker(self, command: str, shell_kind: str, marker_id: str) -> str:
        marker = f"__OPS_AGENT_EXIT_STATUS_{marker_id}__"
        if shell_kind == "powershell":
            if "\n" not in command and "\r" not in command:
                return (
                    "$global:LASTEXITCODE = $null; "
                    f"{command}; "
                    "$__opsAgentSuccess = $?; "
                    "$__opsAgentNativeExit = $global:LASTEXITCODE; "
                    "$__opsAgentExit = if ($null -ne $__opsAgentNativeExit) { [int]$__opsAgentNativeExit } elseif (-not $__opsAgentSuccess) { 1 } else { 0 }; "
                    f"Write-Output \"{marker}:$__opsAgentExit\""
                )
            return (
                "$global:LASTEXITCODE = $null\n"
                f"{command}\n"
                "$__opsAgentSuccess = $?\n"
                "$__opsAgentNativeExit = $global:LASTEXITCODE\n"
                "$__opsAgentExit = if ($null -ne $__opsAgentNativeExit) { [int]$__opsAgentNativeExit } elseif (-not $__opsAgentSuccess) { 1 } else { 0 }\n"
                f"Write-Output \"{marker}:$__opsAgentExit\""
            )
        if shell_kind == "cmd":
            return f"{command}\r\necho {marker}:%ERRORLEVEL%"
        return f"{command}\nprintf '\\n{marker}:%s\\n' \"$?\""

    def _extract_exit_status(self, raw_output: str, marker_id: str) -> int | None:
        plain = ANSI_PATTERN.sub("", raw_output).replace("\r", "")
        marker_prefix = f"__OPS_AGENT_EXIT_STATUS_{marker_id}__"
        for match in EXIT_STATUS_PATTERN.finditer(plain):
            if match.group(0).startswith(marker_prefix):
                try:
                    return int(match.group(2))
                except ValueError:
                    return None
        return None

    def _wait_for_output_idle(self, terminal_id: str) -> None:
        deadline = time.monotonic() + 2.0
        cursor = self.get_output_cursor(terminal_id)
        idle_since = time.monotonic()
        while time.monotonic() < deadline:
            cursor, output = self.read_output_since(terminal_id, cursor)
            if output:
                idle_since = time.monotonic()
            elif time.monotonic() - idle_since >= self.COMMAND_STARTUP_IDLE_SECONDS:
                return
            time.sleep(0.02)

    def _last_prompt_text(self, output: str, shell_kind: str) -> str | None:
        plain = ANSI_PATTERN.sub("", output).replace("\r", "")
        lines = [line.strip() for line in plain.split("\n") if line.strip()]
        for line in reversed(lines):
            if self._line_looks_like_prompt(line, shell_kind):
                return line
            prompt_match = self._prompt_fragment_match(line, shell_kind)
            if prompt_match is not None:
                return prompt_match
        return None

    def _prompt_fragment_match(self, line: str, shell_kind: str) -> str | None:
        stripped = line.strip()
        if shell_kind == "powershell":
            match = re.search(r"PS\s+[^\n]+>\s*$", stripped)
            return match.group(0) if match else None
        if shell_kind == "cmd":
            match = re.search(r"[A-Za-z]:\\[^\n]*>\s*$", stripped)
            return match.group(0) if match else None
        match = re.search(r"[^\n]+[$#>]\s*$", stripped)
        return match.group(0) if match else None

    def _strip_trailing_prompt_fragment(self, output: str, shell_kind: str) -> str:
        if not output:
            return output
        if shell_kind == "powershell":
            return re.sub(r"PS\s+[^\n]+>\s*$", "", output)
        if shell_kind == "cmd":
            return re.sub(r"[A-Za-z]:\\[^\n]*>\s*$", "", output)
        return re.sub(r"[^\s\n]+[$#>]\s*$", "", output)

    def _looks_like_prompt(self, output: str, shell_kind: str, prompt_before: str | None) -> bool:
        prompt = self._last_prompt_text(output, shell_kind)
        if prompt is None:
            return False
        if prompt_before is None:
            return True
        return prompt == prompt_before or self._line_looks_like_prompt(prompt, shell_kind)

    def _line_looks_like_prompt(self, line: str, shell_kind: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        if shell_kind == "powershell":
            return bool(re.search(r"(^|\s)PS\s+.+>\s*$", stripped))
        if shell_kind == "cmd":
            return bool(re.search(r"^[A-Za-z]:\\.*>\s*$", stripped))
        return stripped.endswith(("$", "#", ">"))

    def _extract_natural_command_output(self, raw_output: str, command: str, shell_kind: str) -> str:
        plain = ANSI_PATTERN.sub("", raw_output).replace("\r", "")
        plain = self._strip_trailing_prompt_fragment(plain, shell_kind)
        lines = plain.split("\n")
        end_index = len(lines)
        for index in range(len(lines) - 1, -1, -1):
            if self._line_looks_like_prompt(lines[index], shell_kind):
                end_index = index
                break
        candidate_lines = lines[:end_index]
        start_index = self._find_command_output_start(candidate_lines, command, shell_kind)
        if start_index == 0:
            start_index = self._find_prompt_output_start(candidate_lines, shell_kind)
        output_lines = candidate_lines[start_index:]
        output_lines = self._drop_leading_command_echo(output_lines, command, shell_kind)
        output_lines = self._drop_exit_status_marker_lines(output_lines)
        if output_lines:
            output_lines[0] = self._strip_shell_input_prefix(output_lines[0].strip(), shell_kind)[0]
        while output_lines and not output_lines[0].strip():
            output_lines.pop(0)
        while output_lines and not output_lines[-1].strip():
            output_lines.pop()
        return "\n".join(line.rstrip() for line in output_lines)

    def _drop_exit_status_marker_lines(self, lines: list[str]) -> list[str]:
        return [line for line in lines if "__OPS_AGENT_EXIT_STATUS_" not in line]

    def _drop_leading_command_echo(self, lines: list[str], command: str, shell_kind: str) -> list[str]:
        normalized_command = self._normalize_command_echo(command)
        if not normalized_command:
            return lines

        remaining = list(lines)
        consumed_echo = ""
        while remaining:
            raw_line = remaining[0].strip()
            if not raw_line:
                remaining.pop(0)
                continue

            fragment, had_input_prefix = self._strip_shell_input_prefix(raw_line, shell_kind)
            normalized_fragment = self._normalize_command_echo(fragment)
            if consumed_echo == normalized_command:
                break
            if not normalized_fragment:
                remaining.pop(0)
                continue

            next_consumed = self._normalize_command_echo(consumed_echo + fragment)
            is_initial_echo = not consumed_echo and (
                had_input_prefix
                or normalized_command.startswith(normalized_fragment)
                or normalized_fragment in normalized_command
                or normalized_command in normalized_fragment
            )
            is_echo_continuation = bool(consumed_echo) and (
                next_consumed in normalized_command
                or normalized_command.startswith(next_consumed)
                or normalized_fragment in normalized_command
            )
            if is_initial_echo or is_echo_continuation:
                if next_consumed in normalized_command or normalized_command.startswith(next_consumed):
                    consumed_echo = next_consumed
                elif normalized_command in normalized_fragment:
                    consumed_echo = normalized_command
                elif normalized_fragment in normalized_command:
                    consumed_echo = normalized_fragment
                remaining.pop(0)
                continue
            break
        return remaining

    def _find_command_output_start(self, lines: list[str], command: str, shell_kind: str) -> int:
        command_text = command.strip()
        if not command_text:
            return 0
        normalized_command = self._normalize_command_echo(command_text)
        joined = ""
        for index, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            fragment, _ = self._strip_shell_input_prefix(stripped, shell_kind)
            if not fragment:
                continue
            joined = self._normalize_command_echo(joined + fragment)
            if normalized_command.startswith(joined):
                if joined == normalized_command:
                    return index + 1
                continue
            if joined and not normalized_command.startswith(joined):
                joined = ""
        plain = "\n".join(lines)
        command_index = plain.find(command_text)
        if command_index >= 0:
            consumed = plain[: command_index + len(command_text)]
            return consumed.count("\n")
        return 0

    def _find_prompt_output_start(self, lines: list[str], shell_kind: str) -> int:
        for index, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            fragment, had_input_prefix = self._strip_shell_input_prefix(stripped, shell_kind)
            if self._line_looks_like_prompt(stripped, shell_kind) or self._prompt_fragment_match(stripped, shell_kind) or had_input_prefix:
                return index if fragment else index + 1
        return 0

    def _strip_shell_input_prefix(self, line: str, shell_kind: str) -> tuple[str, bool]:
        stripped = line.strip()
        fragment = self._strip_prompt_prefix(stripped, shell_kind)
        if fragment != stripped:
            return fragment, True
        if shell_kind == "powershell":
            continuation = re.sub(r"^(?:\d+\s*)?>+\s*", "", stripped).strip()
            if continuation != stripped:
                return continuation, True
        return stripped, False

    def _strip_prompt_prefix(self, line: str, shell_kind: str) -> str:
        if shell_kind == "powershell":
            return re.sub(r"^PS\s+.+?>\s*", "", line).strip()
        if shell_kind == "cmd":
            return re.sub(r"^[A-Za-z]:\\.*?>\s*", "", line).strip()
        return re.sub(r"^.*?[$#>]\s*", "", line).strip()

    def _normalize_command_echo(self, value: str) -> str:
        return re.sub(r"\s+", "", value)

    def get_shell_kind(self, terminal_id: str) -> str:
        session_manager = self.get_session(terminal_id)
        if session_manager is None:
            raise ValueError("terminal session not found")
        return session_manager.shell_kind()

    def read_recent_output(self, terminal_id: str) -> str:
        return self.read_buffered_output(terminal_id)

    def read_buffered_output(self, terminal_id: str) -> str:
        runtime = self._sessions.get(terminal_id)
        if runtime is None:
            return ""
        with runtime.buffer_lock:
            chunks = self._output_buffers.get(terminal_id)
            if not chunks:
                return ""
            return "".join(chunk for _, chunk in chunks)

    def get_output_cursor(self, terminal_id: str) -> int:
        runtime = self._sessions.get(terminal_id)
        if runtime is None:
            return self._output_sequences.get(terminal_id, 0)
        with runtime.buffer_lock:
            return self._output_sequences.get(terminal_id, 0)

    def read_output_since(self, terminal_id: str, cursor: int) -> tuple[int, str]:
        runtime = self._sessions.get(terminal_id)
        if runtime is None:
            return cursor, ""
        with runtime.buffer_lock:
            chunks = self._output_buffers.get(terminal_id)
            if not chunks:
                return self._output_sequences.get(terminal_id, cursor), ""
            latest_cursor = cursor
            output_parts: list[str] = []
            for sequence, chunk in chunks:
                if sequence > cursor:
                    output_parts.append(chunk)
                    latest_cursor = sequence
            return latest_cursor, "".join(output_parts)

    def get_command_event_cursor(self, terminal_id: str) -> int:
        runtime = self._sessions.get(terminal_id)
        if runtime is None:
            return self._command_event_sequences.get(terminal_id, 0)
        with runtime.buffer_lock:
            return self._command_event_sequences.get(terminal_id, 0)

    def read_command_events_since(self, terminal_id: str, cursor: int) -> tuple[int, list[dict[str, Any]]]:
        runtime = self._sessions.get(terminal_id)
        if runtime is None:
            return cursor, []
        with runtime.buffer_lock:
            events = self._command_event_buffers.get(terminal_id)
            if not events:
                return self._command_event_sequences.get(terminal_id, cursor), []
            latest_cursor = cursor
            payloads: list[dict[str, Any]] = []
            for sequence, event in events:
                if sequence > cursor:
                    payloads.append(event)
                    latest_cursor = sequence
            return latest_cursor, payloads

    def list_recent_events_for_asset(self, asset_id: int) -> list[dict[str, Any]]:
        # Terminal context is sourced from live in-memory sessions, not persisted history.
        recent_events: list[dict[str, Any]] = []
        with self._registry_lock:
            terminal_ids = [
                terminal_id
                for terminal_id, session_key in self._session_keys.items()
                if session_key == f"asset:{asset_id}" and terminal_id in self._sessions
            ]
        for terminal_id in terminal_ids:
            events = self._command_event_buffers.get(terminal_id, ())
            for sequence, event in events:
                recent_events.append({
                    "id": sequence,
                    "event_type": str(event.get("kind", "terminal_event")),
                    "event_data": json.dumps(event, ensure_ascii=False),
                    "created_at": datetime.now(UTC),
                })
        return recent_events[-50:]

    def _append_output(self, terminal_id: str, output: str) -> str:
        if not output:
            return ""
        runtime = self._sessions.get(terminal_id)
        if runtime is None:
            return ""

        with runtime.buffer_lock:
            visible_output = output
            sequence = self._output_sequences.get(terminal_id, 0) + 1
            self._output_sequences[terminal_id] = sequence
            chunks = self._output_buffers.setdefault(terminal_id, deque(maxlen=4000))
            if chunks.maxlen is not None and len(chunks) == chunks.maxlen:
                self._output_buffer_sizes[terminal_id] = max(
                    0,
                    self._output_buffer_sizes.get(terminal_id, 0) - len(chunks[0][1]),
                )
            chunks.append((sequence, visible_output))
            self._output_buffer_sizes[terminal_id] = self._output_buffer_sizes.get(terminal_id, 0) + len(visible_output)
            self._trim_output_buffer(terminal_id)
        return visible_output

    def _trim_output_buffer(self, terminal_id: str) -> None:
        chunks = self._output_buffers.get(terminal_id)
        if not chunks:
            self._output_buffer_sizes[terminal_id] = 0
            return

        current_size = self._output_buffer_sizes.get(terminal_id, sum(len(chunk) for _, chunk in chunks))
        while current_size > self.MAX_OUTPUT_BUFFER_CHARS and chunks:
            _, removed = chunks.popleft()
            current_size -= len(removed)
        self._output_buffer_sizes[terminal_id] = max(0, current_size)

    def _append_command_event(self, terminal_id: str, event: dict[str, Any]) -> None:
        runtime = self._sessions.get(terminal_id)
        if runtime is None:
            return
        with runtime.buffer_lock:
            sequence = self._command_event_sequences.get(terminal_id, 0) + 1
            self._command_event_sequences[terminal_id] = sequence
            payload = {**event, "sequence": sequence}
            self._command_event_buffers.setdefault(terminal_id, deque(maxlen=8000)).append((sequence, payload))

    def attach_context(self, terminal_id: str, selection_label: str, selected_text: str):
        attachment = build_terminal_context(terminal_id, selection_label, selected_text)
        return attachment

    def _build_session_key(self, asset) -> str:
        asset_id = getattr(asset, "id", None)
        if asset_id is not None:
            return f"asset:{asset_id}"
        return ":".join(
            [
                str(getattr(asset, "asset_type", "")),
                str(getattr(asset, "host", "")),
                str(getattr(asset, "port", "")),
                str(getattr(asset, "username", "")),
            ]
        )
