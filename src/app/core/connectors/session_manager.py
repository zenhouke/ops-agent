import uuid
from collections.abc import Iterable
from typing import cast

from .execution import ExecutionContext, ExecutionEvent, ExecutionResult


class TerminalSessionManager:
    def __init__(self, connector):
        self._connector = connector
        self._channel = None
        self._is_open = False
        self._execution_buffers: dict[str, list[ExecutionEvent]] = {}

    @property
    def channel(self):
        return self._channel

    @property
    def is_open(self) -> bool:
        return self._is_open

    def open(self):
        if self._is_open:
            return self._channel
        self._channel = self._connector.open_interactive()
        self._is_open = True
        return self._channel

    def read(self):
        return self._connector.read()

    def write(self, data: str) -> None:
        self._connector.write(data)

    def shell_kind(self) -> str:
        return getattr(self._connector, "shell_kind", "posix")

    def resize(self, cols: int, rows: int) -> None:
        self._connector.resize(cols, rows)

    def start_execution(
        self,
        command: str,
        context: ExecutionContext | None = None,
        *,
        execution_id: str | None = None,
    ) -> str:
        execution_id = execution_id or str(uuid.uuid4())
        effective_context = context or ExecutionContext()
        starter = getattr(self._connector, "start_execution", None)
        if callable(starter):
            starter(command, effective_context, execution_id)
            self._execution_buffers.setdefault(execution_id, [])
            return execution_id

        runner = getattr(self._connector, "run_command", None)
        if not callable(runner):
            raise NotImplementedError("connector does not support command execution")

        self._execution_buffers[execution_id] = [
            ExecutionEvent(execution_id=execution_id, event_type="started"),
        ]
        output = str(runner(command))
        self._execution_buffers[execution_id].append(
            ExecutionEvent(execution_id=execution_id, event_type="output", text=output)
        )
        self._execution_buffers[execution_id].append(
            ExecutionEvent(
                execution_id=execution_id,
                event_type="completed",
                text=output,
                completed=True,
                success=True,
                exit_code=0,
                completion_reason="exit_code",
                profile="posix-shell",
            )
        )
        return execution_id

    def read_execution_events(self, execution_id: str) -> list[ExecutionEvent]:
        reader = getattr(self._connector, "read_execution_events", None)
        if callable(reader):
            return list(cast(Iterable[ExecutionEvent], reader(execution_id)))
        return list(self._execution_buffers.get(execution_id, []))

    def get_execution_result(self, execution_id: str) -> ExecutionResult:
        getter = getattr(self._connector, "get_execution_result", None)
        if callable(getter):
            return cast(ExecutionResult, getter(execution_id))
        events = self._execution_buffers.get(execution_id, [])
        output = "".join(event.text for event in events if event.event_type == "output")
        completed_event = next((event for event in reversed(events) if event.event_type == "completed"), None)
        if completed_event is None:
            return ExecutionResult(
                execution_id=execution_id,
                output=output,
                completed=False,
                success=False,
                completion_reason="unsupported",
                profile="posix-shell",
            )
        return ExecutionResult(
            execution_id=execution_id,
            output=output,
            completed=completed_event.completed,
            success=completed_event.success,
            needs_attention=completed_event.needs_attention,
            exit_code=completed_event.exit_code,
            completion_reason=completed_event.completion_reason,
            mode=completed_event.mode,
            pager_detected=completed_event.pager_detected,
            profile=completed_event.profile,
            prompt_before=completed_event.prompt_before,
            prompt_after=completed_event.prompt_after,
            matched_error=completed_event.matched_error,
        )

    def collect_network(self, kind: str, *, read_timeout: float = 30.0) -> dict:
        collector = getattr(self._connector, "collect_structured", None)
        if not callable(collector):
            raise ValueError("The authorized terminal is not a supported network device session.")
        return cast(dict, collector(kind, read_timeout=read_timeout))

    def plan_network_collection(self, kind: str) -> dict:
        planner = getattr(self._connector, "collection_plan", None)
        if not callable(planner):
            raise ValueError("The authorized terminal is not a supported network device session.")
        return cast(dict, planner(kind))

    def cancel_execution(self, execution_id: str) -> None:
        canceller = getattr(self._connector, "cancel_execution", None)
        if callable(canceller):
            canceller(execution_id)
            return
        events = self._execution_buffers.get(execution_id)
        if events is None:
            return
        events.append(
            ExecutionEvent(
                execution_id=execution_id,
                event_type="completed",
                completed=True,
                success=False,
                needs_attention=True,
                completion_reason="manual_stop",
                profile="posix-shell",
            )
        )

    def close(self) -> None:
        if not self._is_open:
            return
        self._connector.close()
        self._channel = None
        self._is_open = False
        self._execution_buffers.clear()
