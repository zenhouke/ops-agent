from __future__ import annotations

import uuid
from typing import Any

from app.core.loop.runtime_models import RuntimeState
from app.services.runtime_store import RuntimeStore


class RuntimePersistenceMixin:
    _runtime_store: RuntimeStore

    def _append_runtime_event(
        self: Any,
        runtime: RuntimeState,
        kind: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        with self._state_lock:
            runtime.sequence += 1
            runtime.updated_at = self._now()
            event_id = str(uuid.uuid4())
            occurred_at = runtime.updated_at.isoformat()
            event = {
                **payload,
                "id": payload.get("id") or event_id,
                "kind": kind,
                "eventId": event_id,
                "runtimeId": runtime.runtime_id,
                "sequence": runtime.sequence,
                "ts": occurred_at,
                "occurredAt": occurred_at,
            }
            stored_event = dict(event)
            if "approvalToken" in stored_event:
                stored_event["approvalToken"] = None
            tool_call = stored_event.get("toolCall")
            if isinstance(tool_call, dict) and "approvalToken" in tool_call:
                stored_event["toolCall"] = {**tool_call, "approvalToken": None}
            runtime.events.append(stored_event)
            snapshot = self._runtime_snapshot(runtime, include_secrets=False)
            run_state = self._run_state(runtime)
        self._runtime_store.append_event(snapshot, stored_event, run_state=run_state)
        return event

    def _runtime_snapshot(
        self: Any,
        runtime: RuntimeState,
        *,
        include_secrets: bool = True,
    ) -> dict[str, Any]:
        state = runtime.state
        current_step = state.get_current_step()
        return {
            "runtime_id": runtime.runtime_id,
            "conversation_id": runtime.conversation_id,
            "asset_id": runtime.asset_id,
            "terminal_id": runtime.terminal_id,
            "status": state.phase,
            "run_state": self._run_state(runtime),
            "loaded_skill_name": state.context.loaded_skill_name,
            "mode": state.context.mode,
            "plan_version": state.plan_version,
            "locked_plan": state.locked_plan,
            "steps": [self._step_view(step) for step in state.steps],
            "current_step_id": current_step.step_id if current_step else None,
            "pending_approval_step_id": state.pending_approval_step_id,
            "last_output_excerpt": state.last_output_excerpt,
            "summary": state.summary,
            "error_message": state.error_message,
            "terminal_requests": [
                self._request_view(
                    request,
                    request.approval_token
                    if include_secrets and request.user_decision_status == "pending"
                    else None,
                )
                for request in runtime.terminal_requests.values()
            ],
            "terminal_authorizations": [
                self._authorization_view(authorization)
                for authorization in runtime.terminal_authorizations.values()
            ],
            "created_at": runtime.created_at,
            "updated_at": runtime.updated_at,
            "last_sequence": runtime.sequence,
            "llm_calls": state.llm_calls,
            "tool_calls": state.tool_calls,
            "cancel_requested": state.cancel_requested,
        }

    def _run_state(self: Any, runtime: RuntimeState) -> str:
        if runtime.state.is_terminal():
            return "terminal"
        if runtime.state.phase in {
            "approving",
            "waiting_terminal_approval",
            "waiting_plan_approval",
        }:
            return "waiting"
        return "running" if runtime.execution_lock.locked() else "queued"

    def _persist_runtime(
        self: Any,
        runtime: RuntimeState,
        *,
        run_state: str | None = None,
    ) -> None:
        with self._state_lock:
            snapshot = self._runtime_snapshot(runtime, include_secrets=False)
            next_run_state = run_state or self._run_state(runtime)
        self._runtime_store.save_snapshot(snapshot, run_state=next_run_state)

    def list_runtime_snapshots(self: Any, conversation_id: str) -> list[dict[str, Any]]:
        return self._runtime_store.list_snapshots(conversation_id)

    def recover_persisted_runtimes(self: Any) -> int:
        recovered = self._runtime_store.recover_interrupted()
        self._runtime_store.prune()
        return recovered
