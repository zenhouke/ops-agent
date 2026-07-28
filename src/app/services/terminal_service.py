from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import partial
import json
import re
import logging
import threading
from typing import Any, Awaitable, Callable, TypeVar, cast

import anyio
from starlette.websockets import WebSocketDisconnect

from app.core.connectors.context_bridge import build_terminal_context
from app.core.connectors.session_manager import TerminalSessionManager
from app.core.connectors.ssh_proxy import describe_ssh_proxy_error


T = TypeVar("T")
RunSyncCallable = Callable[..., Awaitable[T]]
run_sync = cast(RunSyncCallable[Any], getattr(anyio.to_thread, "run_sync"))


import uuid


ANSI_PATTERN = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
logger = logging.getLogger(__name__)


@dataclass
class OutputFilterState:
    command_id: str
    start_marker: str
    end_marker: str
    done_marker_prefix: str
    suppressing_input_echo: bool = True
    pending: str = ""
    exit_code: int | None = None


@dataclass
class TerminalSessionRuntime:
    session_manager: TerminalSessionManager
    state: str = "created"
    connection_ids: set[str] = field(default_factory=set)
    last_detached_at: datetime | None = None

class TerminalService:
    SESSION_TTL = timedelta(minutes=15)
    MAX_OUTPUT_BUFFER_CHARS = 256 * 1024

    def __init__(self, connector_factory, persistence=None):
        self._connector_factory = connector_factory
        self._sessions: dict[str, TerminalSessionRuntime] = {}
        self._session_keys: dict[str, str] = {}
        self._output_buffers: dict[str, deque[tuple[int, str]]] = {}
        self._output_buffer_sizes: dict[str, int] = {}
        self._output_sequences: dict[str, int] = {}
        self._output_filters: dict[str, dict[str, OutputFilterState]] = {}
        self._active_filter_ids: dict[str, str | None] = {}
        self._filter_queues: dict[str, deque[str]] = {}
        self._command_event_buffers: dict[str, deque[tuple[int, dict[str, Any]]]] = {}
        self._command_event_sequences: dict[str, int] = {}
        self._state_lock = threading.RLock()

    def _expire_detached_sessions(self) -> None:
        now = datetime.now(UTC)
        expired_ids: list[str] = []
        with self._state_lock:
            for terminal_id, runtime in self._sessions.items():
                if runtime.state == "detached" and runtime.last_detached_at is not None:
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
        with self._state_lock:
            self._sessions[terminal_id] = TerminalSessionRuntime(session_manager=session_manager, state="created")
            self._session_keys[terminal_id] = session_key
            self._output_buffers[terminal_id] = deque(maxlen=4000)
            self._output_buffer_sizes[terminal_id] = 0
            self._output_sequences[terminal_id] = 0
            self._output_filters[terminal_id] = {}
            self._active_filter_ids[terminal_id] = None
            self._filter_queues[terminal_id] = deque()
            self._command_event_buffers[terminal_id] = deque(maxlen=8000)
            self._command_event_sequences[terminal_id] = 0
        return {"terminal_id": terminal_id, "channel": "terminal connected", "error": ""}

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

        buffered_output = self.read_buffered_output(terminal_id)
        if buffered_output:
            await websocket.send_json({"type": "output", "data": buffered_output})

        closed = anyio.Event()
        send_lock = anyio.Lock()
        try:
            async with anyio.create_task_group() as task_group:
                task_group.start_soon(self._receive_websocket_input, terminal_id, runtime, websocket, closed, send_lock)
                task_group.start_soon(self._send_terminal_output, terminal_id, runtime, websocket, closed, send_lock)
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
            if not runtime.connection_ids and terminal_id in self._sessions:
                runtime.state = "detached"
                runtime.last_detached_at = datetime.now(UTC)

    async def _receive_websocket_input(self, terminal_id: str, runtime: TerminalSessionRuntime, websocket, closed, send_lock) -> None:
        try:
            while True:
                message = await websocket.receive_json()
                message_type = message.get("type")
                if message_type == "input":
                    await run_sync(runtime.session_manager.write, message.get("data", ""))
                elif message_type == "resize":
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
                    await run_sync(runtime.session_manager.resize, cols, rows)
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

    async def _send_terminal_output(self, terminal_id: str, runtime: TerminalSessionRuntime, websocket, closed, send_lock) -> None:
        while True:
            output = await run_sync(runtime.session_manager.read)
            if output:
                filtered_output = await run_sync(self._append_output, terminal_id, output)
                try:
                    if filtered_output:
                        async with send_lock:
                            await websocket.send_json({"type": "output", "data": filtered_output})
                except (WebSocketDisconnect, RuntimeError):
                    closed.set()
                    return
            if closed.is_set():
                final_output = await run_sync(runtime.session_manager.read)
                if final_output:
                    await run_sync(self._append_output, terminal_id, final_output)
                return
            await anyio.sleep(0.02)

    def close_session(self, terminal_id: str) -> bool:
        with self._state_lock:
            runtime = self._sessions.pop(terminal_id, None)
            if runtime is None:
                return False
            for store in (
                self._session_keys, self._output_buffers, self._output_buffer_sizes,
                self._output_sequences, self._output_filters, self._active_filter_ids,
                self._filter_queues, self._command_event_buffers, self._command_event_sequences,
            ):
                store.pop(terminal_id, None)
        runtime.session_manager.close()
        return True

    def get_session(self, terminal_id: str):
        runtime = self._sessions.get(terminal_id)
        return runtime.session_manager if runtime is not None else None

    def find_session_id(self, session_key: str) -> str | None:
        with self._state_lock:
            for terminal_id, current_key in self._session_keys.items():
                if current_key == session_key and terminal_id in self._sessions:
                    return terminal_id
        return None

    def session_belongs_to_asset(self, terminal_id: str, asset_id: int) -> bool:
        return self._session_keys.get(terminal_id) == f"asset:{asset_id}" and terminal_id in self._sessions

    def send_input(self, terminal_id: str, data: str, *, output_markers: dict[str, str] | None = None) -> str | None:
        runtime = self._sessions.get(terminal_id)
        if runtime is None:
            raise ValueError("terminal session not found")
        command_id: str | None = None
        if output_markers is not None:
            command_id = str(uuid.uuid4())
            state = OutputFilterState(
                command_id=command_id,
                start_marker=output_markers["start_marker"],
                end_marker=output_markers["end_marker"],
                done_marker_prefix=output_markers["done_marker_prefix"],
            )
            filters = self._output_filters.setdefault(terminal_id, {})
            filters[command_id] = state
            queue = self._filter_queues.setdefault(terminal_id, deque())
            queue.append(command_id)
            if self._active_filter_ids.get(terminal_id) is None:
                self._active_filter_ids[terminal_id] = queue[0]
            self._append_command_event(
                terminal_id,
                {
                    "id": f"command-start-{command_id}",
                    "kind": "command_start",
                    "commandId": command_id,
                    "terminalId": terminal_id,
                    "command": data.strip(),
                },
            )
        normalized = data if data.endswith("\n") else f"{data}\n"
        runtime.session_manager.write(normalized)
        return command_id

    def get_shell_kind(self, terminal_id: str) -> str:
        session_manager = self.get_session(terminal_id)
        if session_manager is None:
            raise ValueError("terminal session not found")
        return session_manager.shell_kind()

    def read_recent_output(self, terminal_id: str) -> str:
        return self.read_buffered_output(terminal_id)

    def read_buffered_output(self, terminal_id: str) -> str:
        if terminal_id not in self._sessions:
            return ""
        chunks = self._output_buffers.get(terminal_id)
        if not chunks:
            return ""
        return "".join(chunk for _, chunk in chunks)

    def get_output_cursor(self, terminal_id: str) -> int:
        return self._output_sequences.get(terminal_id, 0)

    def read_output_since(self, terminal_id: str, cursor: int) -> tuple[int, str]:
        if terminal_id not in self._sessions:
            return cursor, ""
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
        return self._command_event_sequences.get(terminal_id, 0)

    def read_command_events_since(self, terminal_id: str, cursor: int) -> tuple[int, list[dict[str, Any]]]:
        if terminal_id not in self._sessions:
            return cursor, []
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
        for terminal_id, session_key in self._session_keys.items():
            if session_key != f"asset:{asset_id}" or terminal_id not in self._sessions:
                continue
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

        self._derive_command_events(terminal_id, output)
        sequence = self._output_sequences.get(terminal_id, 0) + 1
        self._output_sequences[terminal_id] = sequence
        chunks = self._output_buffers.setdefault(terminal_id, deque(maxlen=4000))
        if chunks.maxlen is not None and len(chunks) == chunks.maxlen:
            self._output_buffer_sizes[terminal_id] = max(
                0,
                self._output_buffer_sizes.get(terminal_id, 0) - len(chunks[0][1]),
            )
        chunks.append((sequence, output))
        self._output_buffer_sizes[terminal_id] = self._output_buffer_sizes.get(terminal_id, 0) + len(output)
        self._trim_output_buffer(terminal_id)
        return output

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

    def _derive_command_events(self, terminal_id: str, output: str) -> None:
        # Raw output stays authoritative for terminal replay; filtered output only drives command cards.
        self._filter_output(terminal_id, output)

    def _append_command_event(self, terminal_id: str, event: dict[str, Any]) -> None:
        sequence = self._command_event_sequences.get(terminal_id, 0) + 1
        self._command_event_sequences[terminal_id] = sequence
        payload = {**event, "sequence": sequence}
        self._command_event_buffers.setdefault(terminal_id, deque(maxlen=8000)).append((sequence, payload))

    def _normalize_output_text(self, output: str) -> str:
        # We return the raw output to preserve ANSI escape codes and carriage returns.
        # This ensures that the terminal emulator on the frontend (xterm.js) can
        # correctly render colors, cursor movements, and other formatting.
        return output

    def _advance_filter_queue(self, terminal_id: str, completed_command_id: str) -> None:
        filters = self._output_filters.get(terminal_id, {})
        filters.pop(completed_command_id, None)
        queue = self._filter_queues.get(terminal_id)
        if queue is None:
            self._active_filter_ids[terminal_id] = None
            return
        while queue and queue[0] == completed_command_id:
            queue.popleft()
        if queue:
            self._active_filter_ids[terminal_id] = queue[0]
        else:
            self._active_filter_ids[terminal_id] = None

    def _filter_output(self, terminal_id: str, output: str) -> str:
        normalized_output = self._normalize_output_text(output)
        active_command_id = self._active_filter_ids.get(terminal_id)
        if active_command_id is None:
            return normalized_output
        state = self._output_filters.get(terminal_id, {}).get(active_command_id)
        if state is None:
            self._active_filter_ids[terminal_id] = None
            return normalized_output

        state.pending += normalized_output
        filtered_parts: list[str] = []

        while True:
            newline_index = state.pending.find("\n")
            if newline_index < 0:
                break

            line = state.pending[: newline_index + 1]
            state.pending = state.pending[newline_index + 1 :]
            normalized_line = line

            if state.suppressing_input_echo:
                if state.start_marker in normalized_line:
                    state.suppressing_input_echo = False
                continue

            if state.start_marker in normalized_line:
                continue

            if state.end_marker in normalized_line:
                trailing = state.pending
                if trailing.strip():
                    self._append_command_event(
                        terminal_id,
                        {
                            "id": f"command-chunk-{state.command_id}-{uuid.uuid4()}",
                            "kind": "command_chunk",
                            "commandId": state.command_id,
                            "terminalId": terminal_id,
                            "stream": "stdout",
                            "text": trailing,
                        },
                    )
                    filtered_parts.append(trailing)
                state.pending = ""
                self._append_command_event(
                    terminal_id,
                    {
                        "id": f"command-end-{state.command_id}",
                        "kind": "command_end",
                        "commandId": state.command_id,
                        "terminalId": terminal_id,
                        "exitCode": state.exit_code,
                    },
                )
                self._advance_filter_queue(terminal_id, state.command_id)
                continue

            if state.done_marker_prefix in normalized_line:
                try:
                    state.exit_code = int(normalized_line.split(state.done_marker_prefix, 1)[1].strip())
                except ValueError:
                    state.exit_code = None
                continue

            self._append_command_event(
                terminal_id,
                {
                    "id": f"command-chunk-{state.command_id}-{uuid.uuid4()}",
                    "kind": "command_chunk",
                    "commandId": state.command_id,
                    "terminalId": terminal_id,
                    "stream": "stdout",
                    "text": line,
                },
            )
            filtered_parts.append(line)

        return "".join(filtered_parts)

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
