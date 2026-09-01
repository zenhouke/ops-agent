#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import threading
import time
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from pydantic import SecretStr

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from app.core.loop.message_manager import MessageManager
from app.core.loop.loop_state import LoopContext, LoopState
from app.core.loop.runtime_manager import LoopRuntimeManager
from app.core.loop.runtime_models import RuntimeTerminalAuthorization
from app.core.loop.state_machine import RuntimeStateTransitionError, transition_runtime_state
from app.core.tool.execute_command import ExecuteCommandHandler
from app.core.connectors.execution import ExecutionContext
from app.core.connectors.local_pty import LocalPtyConnector
from app.core.connectors.session_manager import TerminalSessionManager
from app.services.runtime_store import interruption_recovery
from app.shared.enums import ModelProvider
from app.shared.schemas import ModelConfig


def scenario_text_stream_uses_deltas_and_final_snapshot() -> None:
    manager = MessageManager(runtime_id="eval-message-delta")
    events = [*manager.begin_message(message_type="say", say_type="text")]
    message_id = str(events[0].payload["id"])
    events.extend(manager.update(text="hello "))
    events.extend(manager.update(text="world"))
    events.extend(manager.finalize())

    assert [event.event_type for event in events] == [
        "message_update",
        "delta",
        "delta",
        "message_update",
    ]
    assert events[1].message_id == message_id
    assert events[1].payload["text"] == "hello "
    assert events[2].payload["text"] == "world"
    assert events[3].payload["text"] == "hello world"
    assert events[3].payload["partial"] is False


def scenario_event_window_gap_falls_back_to_durable_store() -> None:
    durable_events = [
        {"id": f"event-{sequence}", "kind": "delta", "sequence": sequence}
        for sequence in range(2, 7)
    ]

    class Store:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        def events_since(self, runtime_id: str, since: int):
            self.calls.append((runtime_id, since))
            return 6, [event for event in durable_events if event["sequence"] > since]

    store = Store()
    manager = LoopRuntimeManager(tools_factory=lambda _: [])
    manager._runtime_store = store  # type: ignore[assignment]
    manager._by_runtime["eval-window"] = SimpleNamespace(
        runtime_id="eval-window",
        conversation_id="eval-conversation",
        state=SimpleNamespace(phase="executing"),
        updated_at=datetime.now(UTC),
        events=deque(durable_events[-2:], maxlen=2),
        sequence=6,
        terminal_requests={},
    )

    latest, recovered = manager.events_since("eval-window", 1)
    assert latest == 6
    assert [event["sequence"] for event in recovered] == [2, 3, 4, 5, 6]
    assert store.calls == [("eval-window", 1)]

    latest, in_memory = manager.events_since("eval-window", 4)
    assert latest == 6
    assert [event["sequence"] for event in in_memory] == [5, 6]
    assert store.calls == [("eval-window", 1)]


def scenario_terminal_authorization_is_runtime_scoped() -> None:
    manager = LoopRuntimeManager(tools_factory=lambda _: [])
    now = datetime.now(UTC)
    authorization = RuntimeTerminalAuthorization(
        authorization_id="authorization-old",
        runtime_id="runtime-old",
        conversation_id="conversation-1",
        asset_id=1,
        asset_name="asset-1",
        terminal_id="terminal-1",
        source="initial_asset",
        approved_by="system",
        request_id=None,
        status="active",
        output_cursor=0,
        created_at=now,
        updated_at=now,
    )
    common = {
        "conversation_id": "conversation-1",
        "state": SimpleNamespace(phase="executing"),
        "updated_at": now,
        "events": deque(),
        "sequence": 0,
        "terminal_requests": {},
    }
    manager._by_runtime["runtime-old"] = SimpleNamespace(
        runtime_id="runtime-old",
        terminal_authorizations={authorization.authorization_id: authorization},
        **common,
    )
    manager._by_runtime["runtime-new"] = SimpleNamespace(
        runtime_id="runtime-new",
        terminal_authorizations={},
        **common,
    )
    manager._by_conversation["conversation-1"] = {
        "runtime-old": manager._by_runtime["runtime-old"],
        "runtime-new": manager._by_runtime["runtime-new"],
    }

    assert manager.resolve_terminal_authorization("runtime-old", authorization.authorization_id) is authorization
    try:
        manager.resolve_terminal_authorization("runtime-new", authorization.authorization_id)
    except ValueError as exc:
        assert str(exc) == "terminal authorization is not active"
    else:
        raise AssertionError("A terminal authorization from another runtime was accepted")


def scenario_command_scope_rechecks_asset_allowlist() -> None:
    state = SimpleNamespace(context=SimpleNamespace(
        asset_id=1,
        conversation_primary_asset_id=1,
        conversation_scope_mode="single",
        allowed_asset_ids=[1],
    ))
    assert ExecuteCommandHandler._scope_error(state, 1) is None
    assert "allowlist" in str(ExecuteCommandHandler._scope_error(state, 2))


def scenario_cancel_terminalizes_runtime_and_revokes_secrets() -> None:
    class Store:
        def save_snapshot(self, snapshot, *, run_state):
            _ = snapshot, run_state

        def append_event(self, snapshot, event, *, run_state):
            _ = snapshot, event, run_state

    manager = LoopRuntimeManager(tools_factory=lambda _: [])
    manager._runtime_store = Store()  # type: ignore[assignment]
    context = LoopContext(
        runtime_id="runtime-cancel",
        conversation_id="conversation-cancel",
        asset_id=1,
        asset_type="linux",
        terminal_id="terminal-1",
        asset_summary="asset-1",
        shell_type="bash",
        os_type="linux",
        user_prompt="run",
        model_config=ModelConfig(
            provider=ModelProvider.OPENAI_COMPATIBLE,
            model_name="runtime-eval",
            base_url="http://invalid",
            api_key=SecretStr("unused"),
        ),
        conversation_primary_asset_id=1,
        allowed_asset_ids=[1],
    )
    state = manager.create_runtime(
        conversation_id=context.conversation_id,
        asset_id=1,
        terminal_id="terminal-1",
        context=context,
    )
    state.pending_approval_token = "secret"
    state.pending_approval_token_hash = "hash"
    cancelled_execution_ids: list[str] = []
    session_manager = SimpleNamespace(
        cancel_execution=lambda execution_id: cancelled_execution_ids.append(execution_id)
    )
    terminal_service = SimpleNamespace(
        get_session=lambda terminal_id: session_manager if terminal_id == "terminal-1" else None
    )
    state.active_terminal_id = "terminal-1"
    state.active_execution_id = "execution-1"
    result = manager.cancel(context.runtime_id, terminal_service=terminal_service)
    snapshot = manager.get_snapshot(context.runtime_id)

    assert result["status"] == "failed"
    assert state.cancel_requested is True
    assert snapshot["run_state"] == "terminal"
    assert snapshot["pending_approval_token"] is None
    assert snapshot["error_message"] == "Cancelled by operator."
    assert cancelled_execution_ids == ["execution-1"]
    assert snapshot["active_terminal_id"] is None
    assert snapshot["active_execution_id"] is None


def scenario_runtime_state_machine_rejects_invalid_transitions() -> None:
    context = LoopContext(
        runtime_id="runtime-state-machine",
        conversation_id="conversation-state-machine",
        asset_id=1,
        asset_type="linux",
        terminal_id=None,
        asset_summary="asset-1",
        shell_type="bash",
        os_type="linux",
        user_prompt="run",
        model_config=ModelConfig(
            provider=ModelProvider.OPENAI_COMPATIBLE,
            model_name="runtime-eval",
            base_url="http://invalid",
            api_key=SecretStr("unused"),
        ),
    )
    state = LoopState(phase="executing", context=context)
    try:
        transition_runtime_state(state, "approving")
    except RuntimeStateTransitionError as exc:
        assert "pending_tool_call_id" in str(exc)
    else:
        raise AssertionError("Incomplete approval state was accepted")

    transition_runtime_state(state, "completed")
    try:
        transition_runtime_state(state, "executing")
    except RuntimeStateTransitionError as exc:
        assert "completed -> executing" in str(exc)
    else:
        raise AssertionError("Terminal runtime was resumed")


def scenario_local_execution_can_be_cancelled() -> None:
    connector = LocalPtyConnector()
    manager = TerminalSessionManager(connector)
    execution_id = "eval-cancellable-execution"
    worker = threading.Thread(
        target=lambda: manager.start_execution(
            "sleep 5",
            ExecutionContext(timeout_seconds=10),
            execution_id=execution_id,
        ),
        daemon=True,
    )
    started = time.monotonic()
    worker.start()
    deadline = time.monotonic() + 2
    while worker.is_alive() and not connector._execution_processes and time.monotonic() < deadline:
        time.sleep(0.01)
    manager.cancel_execution(execution_id)
    worker.join(timeout=2)
    assert not worker.is_alive()
    result = manager.get_execution_result(execution_id)
    assert result.completion_reason == "manual_stop"
    assert result.success is False
    assert time.monotonic() - started < 3


def scenario_interrupted_runtime_exposes_safe_recovery_action() -> None:
    assert interruption_recovery("approving") == ("restart_and_reapprove", "command_approval")
    assert interruption_recovery("waiting_user_input") == (
        "restart_with_operator_reply",
        "operator_input",
    )
    assert interruption_recovery("executing") == ("restart_from_conversation", "agent_execution")

def main() -> int:
    scenarios = [
        ("text_stream_uses_deltas_and_final_snapshot", scenario_text_stream_uses_deltas_and_final_snapshot),
        ("event_window_gap_falls_back_to_durable_store", scenario_event_window_gap_falls_back_to_durable_store),
        ("terminal_authorization_is_runtime_scoped", scenario_terminal_authorization_is_runtime_scoped),
        ("command_scope_rechecks_asset_allowlist", scenario_command_scope_rechecks_asset_allowlist),
        ("cancel_terminalizes_runtime_and_revokes_secrets", scenario_cancel_terminalizes_runtime_and_revokes_secrets),
        ("runtime_state_machine_rejects_invalid_transitions", scenario_runtime_state_machine_rejects_invalid_transitions),
        ("local_execution_can_be_cancelled", scenario_local_execution_can_be_cancelled),
        ("interrupted_runtime_exposes_safe_recovery_action", scenario_interrupted_runtime_exposes_safe_recovery_action),
    ]
    results: list[dict[str, str]] = []
    for name, scenario in scenarios:
        try:
            scenario()
        except Exception as exc:
            results.append({"name": name, "status": "failed", "error": str(exc)})
        else:
            results.append({"name": name, "status": "passed"})
    report = {
        "suite": "runtime-events",
        "passed": sum(item["status"] == "passed" for item in results),
        "total": len(results),
        "scenarios": results,
    }
    report["status"] = "passed" if report["passed"] == report["total"] else "failed"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
