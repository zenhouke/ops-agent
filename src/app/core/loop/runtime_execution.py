from __future__ import annotations

import hashlib
import secrets
import time
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Literal

from app.core.llm.types import LLMMessage
from app.core.loop.agent_loop import AgentLoop
from app.core.loop.loop_events import LoopEvent
from app.core.loop.loop_state import LoopContext, LoopRuntimeStep, LoopState
from app.core.loop.runtime_models import (
    PendingTerminalRequest,
    RuntimeState,
    RuntimeTerminalAuthorization,
)
from app.core.runtime.control import (
    RuntimeBudgetExceededError,
    RuntimeCancelledError,
    get_runtime_control,
)


class RuntimeExecutionMixin:
    def _request_view(
        self: Any,
        request: PendingTerminalRequest,
        approval_token: str | None = None,
    ) -> dict[str, Any]:
        return {
            "requestId": request.request_id,
            "runtimeId": request.runtime_id,
            "assetId": request.asset_id,
            "assetName": request.asset_name,
            "reason": request.reason,
            "userDecisionStatus": request.user_decision_status,
            "terminalCreationStatus": request.terminal_creation_status,
            "expiresAt": request.expires_at.isoformat(),
            "approvalToken": approval_token,
            "failureReason": request.failure_reason,
        }

    def _authorization_view(
        self: Any,
        authorization: RuntimeTerminalAuthorization,
    ) -> dict[str, Any]:
        return {
            "authorizationId": authorization.authorization_id,
            "runtimeId": authorization.runtime_id,
            "assetId": authorization.asset_id,
            "assetName": authorization.asset_name,
            "terminalId": authorization.terminal_id,
            "source": authorization.source,
            "approvedBy": authorization.approved_by,
            "requestId": authorization.request_id,
            "status": authorization.status,
            "assetType": authorization.asset_type,
            "shellType": authorization.shell_type,
            "osType": authorization.os_type,
            "executionProfile": authorization.execution_profile,
            "deviceVendor": authorization.device_vendor,
            "replacedByAuthorizationId": authorization.replaced_by_authorization_id,
            "revokeReason": authorization.revoke_reason,
        }

    def create_runtime(
        self: Any,
        *,
        conversation_id: str,
        asset_id: int,
        terminal_id: str | None,
        context: LoopContext,
    ) -> LoopState:
        self._expire_completed_runtimes()
        limits = get_runtime_control().limits
        state = LoopState(
            phase="executing",
            context=context,
            deadline_monotonic=time.monotonic() + limits.runtime_timeout_seconds,
            max_llm_calls=limits.max_llm_calls,
            max_tool_calls=limits.max_tool_calls,
        )
        runtime = RuntimeState(
            runtime_id=context.runtime_id,
            conversation_id=conversation_id,
            asset_id=asset_id,
            terminal_id=terminal_id,
            state=state,
            events=deque(maxlen=2000),
            sequence=0,
            created_at=self._now(),
            updated_at=self._now(),
        )
        with self._state_lock:
            self._by_runtime[context.runtime_id] = runtime
            self._by_conversation.setdefault(conversation_id, {})[context.runtime_id] = runtime
        self._persist_runtime(runtime, run_state="queued")
        return state

    def get_runtime(self: Any, runtime_id: str) -> RuntimeState | None:
        self._expire_completed_runtimes()
        with self._state_lock:
            return self._by_runtime.get(runtime_id)

    def list_runtimes(self: Any, conversation_id: str) -> list[RuntimeState]:
        self._expire_completed_runtimes()
        with self._state_lock:
            return list(self._by_conversation.get(conversation_id, {}).values())

    def events_since(self: Any, runtime_id: str, since: int) -> tuple[int, list[dict]]:
        runtime = self.get_runtime(runtime_id)
        if runtime is None:
            return self._runtime_store.events_since(runtime_id, since)
        self._expire_terminal_requests(runtime)
        with self._state_lock:
            events = [event for event in runtime.events if int(event.get("sequence", 0)) > since]
            return runtime.sequence, events

    def get_snapshot(self: Any, runtime_id: str) -> dict:
        runtime = self.get_runtime(runtime_id)
        if runtime is None:
            snapshot = self._runtime_store.get_snapshot(runtime_id)
            if snapshot is None:
                raise ValueError("runtime not found")
            return snapshot
        self._expire_terminal_requests(runtime)
        return self._runtime_snapshot(runtime)

    def _step_view(self: Any, step: LoopRuntimeStep) -> dict[str, Any]:
        return {
            "step_id": step.step_id,
            "title": step.title,
            "command": "",
            "reason": step.reason,
            "risk_level": step.risk_level,
            "working_directory": step.working_directory,
            "expected_output": step.expected_output,
            "status": step.status,
            "output": step.output,
            "exit_code": step.exit_code,
        }

    def cancel(self: Any, runtime_id: str, reason: str = "Cancelled by operator.") -> dict[str, Any]:
        runtime = self.get_runtime(runtime_id)
        if runtime is None:
            raise ValueError("runtime not found")
        state = runtime.state
        if state.is_terminal():
            return {"runtimeId": runtime_id, "status": state.phase, "alreadyTerminal": True}
        state.cancel_requested = True
        state.cancellation_reason = reason
        get_runtime_control().metrics.run_finished(runtime_id, status="cancelled")
        if state.phase in {"approving", "waiting_terminal_approval"}:
            state.phase = "failed"
            state.error_message = reason
        event = self._append_runtime_event(runtime, "error", {
            "text": reason,
            "recoverable": False,
            "cancelled": True,
        })
        return {"runtimeId": runtime_id, "status": state.phase, "event": event}

    @contextmanager
    def _execution(self: Any, runtime: RuntimeState) -> Iterator[None]:
        if not runtime.execution_lock.acquire(blocking=False):
            raise RuntimeError("Runtime is already executing.")
        try:
            self._persist_runtime(runtime, run_state="running")
            yield
        finally:
            runtime.execution_lock.release()
            self._persist_runtime(runtime)

    def _iterate_loop(self: Any, runtime: RuntimeState, iterator: Iterator[LoopEvent]) -> Iterator[dict]:
        try:
            for event in iterator:
                yield self._to_ws_event(event, runtime)
                usage_event = self._build_usage_event(runtime)
                if usage_event is not None:
                    yield usage_event
        except RuntimeCancelledError as exc:
            runtime.state.phase = "failed"
            runtime.state.error_message = str(exc)
            yield self._append_runtime_event(runtime, "error", {
                "text": str(exc),
                "recoverable": False,
                "cancelled": True,
            })
        except RuntimeBudgetExceededError as exc:
            runtime.state.phase = "failed"
            runtime.state.error_message = str(exc)
            yield self._append_runtime_event(runtime, "error", {
                "text": str(exc),
                "recoverable": False,
                "budgetExceeded": True,
            })

    def run(self: Any, *, runtime_id: str, terminal_service: Any) -> Iterator[dict]:
        runtime = self.get_runtime(runtime_id)
        if runtime is None:
            raise ValueError("runtime not found")
        loop = AgentLoop(tools=self._tools_factory(terminal_service), usage_callback=self._usage_callback)
        with self._execution(runtime):
            yield from self._iterate_loop(runtime, loop.run(runtime.state))

    def resume(
        self: Any,
        *,
        runtime_id: str,
        approved: bool,
        approval_token: str | None,
        terminal_service: Any,
    ) -> Iterator[dict]:
        runtime = self.get_runtime(runtime_id)
        if runtime is None:
            raise ValueError("runtime not found")
        expected_token_hash = runtime.state.pending_approval_token_hash
        if expected_token_hash is None:
            raise ValueError("approval token is not available")
        if approval_token is None or not secrets.compare_digest(
            expected_token_hash,
            hashlib.sha256(approval_token.encode("utf-8")).hexdigest(),
        ):
            raise PermissionError("invalid approval token")
        loop = AgentLoop(tools=self._tools_factory(terminal_service), usage_callback=self._usage_callback)
        with self._execution(runtime):
            yield from self._iterate_loop(runtime, loop.resume_with_approval(runtime.state, approved=approved))

    def resume_after_terminal_request(
        self: Any,
        *,
        runtime_id: str,
        resume_message: str,
        terminal_service: Any,
        authorization_id: str | None = None,
    ) -> Iterator[dict]:
        runtime = self.get_runtime(runtime_id)
        if runtime is None:
            raise ValueError("runtime not found")
        runtime.state.phase = "executing"
        runtime.state.context.default_authorization_id = (
            authorization_id
            or self._latest_active_authorization_id(runtime)
            or runtime.state.context.default_authorization_id
        )
        runtime.state.messages.append(
            LLMMessage(role="user", content=self._terminal_request_resume_prompt(runtime, resume_message))
        )
        loop = AgentLoop(tools=self._tools_factory(terminal_service), usage_callback=self._usage_callback)
        with self._execution(runtime):
            yield from self._iterate_loop(runtime, loop.run(runtime.state))

    def _terminal_request_resume_prompt(
        self: Any,
        runtime: RuntimeState,
        resume_message: str,
    ) -> str:
        authorizations = [
            authorization
            for authorization in runtime.terminal_authorizations.values()
            if authorization.status == "active"
        ]
        lines = [
            "\n".join([
                f"- {item.asset_name} (asset_id={item.asset_id}) authorization_id={item.authorization_id}",
                f"  Asset Type: {item.asset_type or 'unknown'}",
                f"  Shell: {item.shell_type}",
                f"  Operating System Type: {item.os_type}",
                f"  Execution Profile: {item.execution_profile}",
                f"  Device Vendor: {item.device_vendor or 'unknown'}",
                f"  Current Host Information: {item.asset_summary}",
                f"  Device Execution Rules:\n{item.device_context}" if item.device_context else "  Device Execution Rules: none",
            ])
            for item in authorizations
        ]
        summary = "\n".join(lines) if lines else "- None"
        return (
            f"Terminal request result: {resume_message}\n\n"
            f"Original task: {runtime.state.context.user_prompt}\n\n"
            f"Active terminal authorizations for this runtime:\n{summary}\n\n"
            "Continue the original task. Request terminal access for any missing asset, and use "
            "execute_command with the matching authorization_id for each authorized asset."
        )

    def _latest_active_authorization_id(self: Any, runtime: RuntimeState) -> str | None:
        active = [
            item for item in runtime.terminal_authorizations.values()
            if item.status == "active"
        ]
        return max(active, key=lambda item: item.created_at).authorization_id if active else None

    def _context_percent_for_tokens(self: Any, token_count: int, model_config: Any) -> int:
        model_name = model_config.model_name.lower()
        context_window = 200_000 if "claude" in model_name else 128_000 if any(
            name in model_name for name in ("gpt-4", "gpt-5")
        ) else 32_000
        return min(100, max(0, round(token_count * 100 / max(1, context_window - 4_000))))

    def _context_status_for_percent(
        self: Any,
        context_percent: int,
    ) -> Literal["normal", "warning", "critical"]:
        return "critical" if context_percent >= 90 else "warning" if context_percent >= 70 else "normal"

    def _build_usage_event(self: Any, runtime: RuntimeState) -> dict | None:
        state = runtime.state
        usage = state.latest_usage if self._usage_callback is not None else None
        if usage is None:
            return None
        state.latest_usage = None
        percent = self._context_percent_for_tokens(int(usage.get("totalTokens") or 0), state.context.model_config)
        return self._append_runtime_event(runtime, "context_status", {
            "contextPercent": percent,
            "contextStatus": self._context_status_for_percent(percent),
            "tokenUsage": usage,
        })

    def _to_ws_event(self: Any, event: LoopEvent, runtime: RuntimeState) -> dict:
        kind = event.event_type.replace("loop_", "")
        payload = dict(event.payload)
        for key, value in (("messageId", event.message_id), ("stage", event.stage), ("stepId", event.step_id)):
            if value:
                payload[key] = value
        return self._append_runtime_event(runtime, kind, payload)
