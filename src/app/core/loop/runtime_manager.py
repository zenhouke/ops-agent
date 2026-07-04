from __future__ import annotations

import hashlib
import secrets
import uuid
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Literal

from app.core.connectors.device_profiles import select_device_profile, select_execution_profile
from app.core.connectors.execution_context import build_asset_summary, build_device_context, infer_os_type
from app.core.loop.agent_loop import AgentLoop
from app.core.loop.loop_events import LoopEvent
from app.core.loop.loop_state import LoopContext, LoopRuntimeStep, LoopState
from app.core.llm.types import LLMMessage


TerminalRequestDecisionStatus = Literal["pending", "approved", "rejected", "expired"]
TerminalCreationStatus = Literal["not_started", "opening", "opened", "failed"]
TerminalAuthorizationStatus = Literal["active", "revoked", "closed", "expired", "replaced"]
TerminalAuthorizationSource = Literal["initial_asset", "user_approved_request"]
TerminalAuthorizationApprover = Literal["system", "user"]


@dataclass
class PendingTerminalRequest:
    request_id: str
    runtime_id: str
    conversation_id: str
    asset_id: int
    asset_name: str
    reason: str
    token_hash: str
    user_decision_status: TerminalRequestDecisionStatus
    terminal_creation_status: TerminalCreationStatus
    created_at: datetime
    expires_at: datetime
    decided_at: datetime | None = None
    terminal_started_at: datetime | None = None
    terminal_finished_at: datetime | None = None
    failure_reason: str | None = None
    approval_token: str | None = None


@dataclass
class RuntimeTerminalAuthorization:
    authorization_id: str
    runtime_id: str
    conversation_id: str
    asset_id: int
    asset_name: str
    terminal_id: str
    source: TerminalAuthorizationSource
    approved_by: TerminalAuthorizationApprover
    request_id: str | None
    status: TerminalAuthorizationStatus
    output_cursor: int
    created_at: datetime
    updated_at: datetime
    asset_type: str = ""
    asset_summary: str = ""
    shell_type: str = "unknown"
    os_type: str = "unknown"
    execution_profile: str = "posix-shell"
    device_vendor: str | None = None
    device_context: str = ""
    revoked_at: datetime | None = None
    revoke_reason: str | None = None
    replaced_by_authorization_id: str | None = None


@dataclass
class RuntimeState:
    runtime_id: str
    conversation_id: str
    asset_id: int
    terminal_id: str | None
    state: LoopState
    events: deque[dict]
    sequence: int
    created_at: datetime
    updated_at: datetime
    terminal_requests: dict[str, PendingTerminalRequest] = field(default_factory=dict)
    terminal_authorizations: dict[str, RuntimeTerminalAuthorization] = field(default_factory=dict)


class LoopRuntimeManager:
    COMPLETED_RUNTIME_TTL = timedelta(minutes=30)

    def __init__(self, *, tools_factory, usage_callback=None):
        self._tools_factory = tools_factory
        self._usage_callback = usage_callback
        self._by_runtime: dict[str, RuntimeState] = {}
        self._by_conversation: dict[str, dict[str, RuntimeState]] = {}
        self._terminal_slots: dict[str, str] = {}

    def _now(self) -> datetime:
        return datetime.now(UTC)

    def _hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _expire_completed_runtimes(self) -> None:
        now = self._now()
        expired_runtime_ids = [
            runtime_id
            for runtime_id, runtime in self._by_runtime.items()
            if runtime.state.phase in {"completed", "failed", "cancelled"}
            and now - runtime.updated_at >= self.COMPLETED_RUNTIME_TTL
        ]
        for runtime_id in expired_runtime_ids:
            runtime = self._by_runtime.pop(runtime_id, None)
            if runtime is None:
                continue
            conversation_runtimes = self._by_conversation.get(runtime.conversation_id)
            if conversation_runtimes is not None:
                conversation_runtimes.pop(runtime_id, None)
                if not conversation_runtimes:
                    self._by_conversation.pop(runtime.conversation_id, None)
            for terminal_id, owner_runtime_id in list(self._terminal_slots.items()):
                if owner_runtime_id == runtime_id:
                    self._terminal_slots.pop(terminal_id, None)

    def _request_view(self, request: PendingTerminalRequest, approval_token: str | None = None) -> dict[str, Any]:
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

    def _authorization_view(self, authorization: RuntimeTerminalAuthorization) -> dict[str, Any]:
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

    def _append_runtime_event(self, runtime: RuntimeState, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        runtime.sequence += 1
        runtime.updated_at = self._now()
        event_id = str(uuid.uuid4())
        occurred_at = runtime.updated_at.isoformat()
        event = {
            "id": event_id,
            "kind": kind,
            "eventId": event_id,
            "runtimeId": runtime.runtime_id,
            "sequence": runtime.sequence,
            "ts": occurred_at,
            "occurredAt": occurred_at,
            **payload,
        }
        stored_event = dict(event)
        if "approvalToken" in stored_event:
            stored_event["approvalToken"] = None
        runtime.events.append(stored_event)
        return event

    def _authorization_context_from_asset(self, asset: Any, terminal_service: Any, terminal_id: str) -> dict[str, Any]:
        asset_type = str(getattr(asset, "asset_type", "") or "")
        try:
            shell_type = terminal_service.get_shell_kind(terminal_id)
        except ValueError:
            shell_type = "unknown"
        execution_profile = select_execution_profile(asset_type, shell_type)
        device_profile = select_device_profile(asset_type, shell_type)
        return {
            "asset_type": asset_type,
            "asset_summary": build_asset_summary(asset),
            "shell_type": shell_type,
            "os_type": infer_os_type(shell_type, execution_profile=execution_profile),
            "execution_profile": execution_profile,
            "device_vendor": device_profile.vendor if device_profile else None,
            "device_context": build_device_context(execution_profile, device_profile),
        }

    def _authorization_context_from_runtime(self, context: LoopContext) -> dict[str, Any]:
        return {
            "asset_type": context.asset_type,
            "asset_summary": context.asset_summary,
            "shell_type": context.shell_type,
            "os_type": context.os_type,
            "execution_profile": context.execution_profile,
            "device_vendor": context.device_vendor,
            "device_context": context.device_context,
        }

    def create_initial_terminal_authorization(
        self,
        runtime_id: str,
        *,
        conversation_id: str,
        asset_id: int,
        asset_name: str,
        terminal_id: str,
    ) -> RuntimeTerminalAuthorization:
        runtime = self._by_runtime.get(runtime_id)
        if runtime is None:
            raise ValueError("runtime not found")
        existing = next(
            (
                authorization
                for authorization in runtime.terminal_authorizations.values()
                if authorization.terminal_id == terminal_id and authorization.status == "active"
            ),
            None,
        )
        if existing is not None:
            return existing
        now = self._now()
        context_values = self._authorization_context_from_runtime(runtime.state.context)
        authorization = RuntimeTerminalAuthorization(
            authorization_id=str(uuid.uuid4()),
            runtime_id=runtime_id,
            conversation_id=conversation_id,
            asset_id=asset_id,
            asset_name=asset_name,
            terminal_id=terminal_id,
            source="initial_asset",
            approved_by="system",
            request_id=None,
            status="active",
            output_cursor=0,
            created_at=now,
            updated_at=now,
            **context_values,
        )
        runtime.terminal_authorizations[authorization.authorization_id] = authorization
        self._append_runtime_event(
            runtime,
            "terminal_session_opened",
            {
                "runtimeId": runtime_id,
                "requestId": None,
                "authorizationId": authorization.authorization_id,
                "assetId": asset_id,
                "assetName": asset_name,
                "terminalId": terminal_id,
                "channel": "initial terminal authorized",
            },
        )
        return authorization

    def _expire_terminal_requests(self, runtime: RuntimeState) -> None:
        now = self._now()
        for request in runtime.terminal_requests.values():
            if request.user_decision_status != "pending" or request.expires_at > now:
                continue
            request.user_decision_status = "expired"
            request.decided_at = now
            request.approval_token = None
            runtime.updated_at = now
            for event in runtime.events:
                if event.get("kind") == "terminal_session_request" and event.get("requestId") == request.request_id:
                    event["approvalToken"] = None
                    event["userDecisionStatus"] = "expired"
            self._append_runtime_event(
                runtime,
                "terminal_session_rejected",
                {
                    "runtimeId": runtime.runtime_id,
                    "requestId": request.request_id,
                    "assetId": request.asset_id,
                    "assetName": request.asset_name,
                    "reason": "expired",
                    "userDecisionStatus": "expired",
                    "terminalCreationStatus": request.terminal_creation_status,
                    "approvalToken": None,
                },
            )

    def create_terminal_request(
        self,
        runtime_id: str,
        *,
        conversation_id: str,
        asset_id: int,
        asset_name: str,
        reason: str,
        ttl_seconds: int = 300,
    ) -> tuple[PendingTerminalRequest, str, dict[str, Any]]:
        runtime = self._by_runtime.get(runtime_id)
        if runtime is None:
            raise ValueError("runtime not found")
        if ttl_seconds <= 0:
            raise ValueError("terminal request TTL must be positive")
        approval_token = secrets.token_urlsafe(32)
        now = self._now()
        request = PendingTerminalRequest(
            request_id=str(uuid.uuid4()),
            runtime_id=runtime_id,
            conversation_id=conversation_id,
            asset_id=asset_id,
            asset_name=asset_name,
            reason=reason,
            token_hash=self._hash_token(approval_token),
            user_decision_status="pending",
            terminal_creation_status="not_started",
            created_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
            approval_token=approval_token,
        )
        runtime.terminal_requests[request.request_id] = request
        event = self._append_runtime_event(
            runtime,
            "terminal_session_request",
            self._request_view(request, approval_token),
        )
        return request, approval_token, event

    def has_active_initial_authorization(self, runtime_id: str, asset_id: int) -> bool:
        runtime = self._by_runtime.get(runtime_id)
        if runtime is None:
            raise ValueError("runtime not found")
        return any(
            authorization.asset_id == asset_id
            and authorization.source == "initial_asset"
            and authorization.status == "active"
            for authorization in runtime.terminal_authorizations.values()
        )

    def _find_active_authorization_for_request(
        self,
        runtime: RuntimeState,
        request_id: str,
    ) -> RuntimeTerminalAuthorization | None:
        return next(
            (
                authorization
                for authorization in runtime.terminal_authorizations.values()
                if authorization.request_id == request_id and authorization.status == "active"
            ),
            None,
        )

    def _terminal_request_decision_response(
        self,
        request: PendingTerminalRequest,
        authorization: RuntimeTerminalAuthorization | None = None,
        *,
        already_decided: bool = False,
    ) -> dict[str, Any]:
        return {
            "status": request.user_decision_status,
            "alreadyDecided": already_decided,
            "requestId": request.request_id,
            "authorizationId": authorization.authorization_id if authorization else None,
            "assetId": request.asset_id,
            "assetName": request.asset_name,
            "terminalId": authorization.terminal_id if authorization else None,
            "terminalCreationStatus": request.terminal_creation_status,
            "channel": "terminal connected" if authorization else None,
            "failureReason": request.failure_reason,
        }

    async def decide_terminal_request(
        self,
        runtime_id: str,
        request_id: str,
        *,
        approval_token: str,
        approved: bool,
        terminal_service: Any,
        asset: Any,
    ) -> dict[str, Any]:
        runtime = self._by_runtime.get(runtime_id)
        if runtime is None:
            raise ValueError("runtime not found")
        if runtime.state.cancel_requested or runtime.state.is_terminal():
            raise ValueError("runtime is already terminal")
        self._expire_terminal_requests(runtime)
        request = runtime.terminal_requests.get(request_id)
        if request is None or request.runtime_id != runtime_id:
            raise KeyError("terminal request not found")
        if not secrets.compare_digest(request.token_hash, self._hash_token(approval_token)):
            raise PermissionError("invalid terminal request token")
        now = self._now()
        if request.user_decision_status != "pending":
            return self._terminal_request_decision_response(
                request,
                self._find_active_authorization_for_request(runtime, request.request_id),
                already_decided=True,
            )
        request.decided_at = now
        request.approval_token = None
        for event in runtime.events:
            if event.get("kind") == "terminal_session_request" and event.get("requestId") == request.request_id:
                event["approvalToken"] = None
        if not approved:
            request.user_decision_status = "rejected"
            self._append_runtime_event(
                runtime,
                "terminal_session_rejected",
                {
                    "runtimeId": runtime_id,
                    "requestId": request.request_id,
                    "assetId": request.asset_id,
                    "assetName": request.asset_name,
                    "reason": "user rejected",
                    "userDecisionStatus": request.user_decision_status,
                    "terminalCreationStatus": request.terminal_creation_status,
                    "approvalToken": None,
                    "failureReason": request.failure_reason,
                },
            )
            return self._terminal_request_decision_response(request)
        request.user_decision_status = "approved"
        request.terminal_creation_status = "opening"
        request.terminal_started_at = now
        try:
            result = terminal_service.open_session(asset)
        except Exception as exc:
            result = {"terminal_id": None, "channel": None, "error": str(exc)}
        terminal_id = result.get("terminal_id")
        if not terminal_id:
            request.terminal_creation_status = "failed"
            request.terminal_finished_at = self._now()
            request.failure_reason = str(result.get("error") or "terminal open failed")
            self._append_runtime_event(
                runtime,
                "terminal_session_rejected",
                {
                    "runtimeId": runtime_id,
                    "requestId": request.request_id,
                    "assetId": request.asset_id,
                    "assetName": request.asset_name,
                    "reason": request.failure_reason,
                    "userDecisionStatus": request.user_decision_status,
                    "terminalCreationStatus": request.terminal_creation_status,
                    "approvalToken": None,
                    "failureReason": request.failure_reason,
                },
            )
            return self._terminal_request_decision_response(request)
        request.terminal_creation_status = "opened"
        request.terminal_finished_at = self._now()
        context_values = self._authorization_context_from_asset(asset, terminal_service, terminal_id)
        authorization = RuntimeTerminalAuthorization(
            authorization_id=str(uuid.uuid4()),
            runtime_id=runtime_id,
            conversation_id=request.conversation_id,
            asset_id=request.asset_id,
            asset_name=request.asset_name,
            terminal_id=terminal_id,
            source="user_approved_request",
            approved_by="user",
            request_id=request.request_id,
            status="active",
            output_cursor=0,
            created_at=request.terminal_finished_at,
            updated_at=request.terminal_finished_at,
            **context_values,
        )
        runtime.terminal_authorizations[authorization.authorization_id] = authorization
        self._append_runtime_event(
            runtime,
            "terminal_session_opened",
            {
                "runtimeId": runtime_id,
                "requestId": request.request_id,
                "authorizationId": authorization.authorization_id,
                "assetId": request.asset_id,
                "assetName": request.asset_name,
                "terminalId": authorization.terminal_id,
                "channel": result.get("channel") or "terminal connected",
            },
        )
        return {
            "status": "approved",
            "requestId": request.request_id,
            "authorizationId": authorization.authorization_id,
            "assetId": request.asset_id,
            "assetName": request.asset_name,
            "terminalId": authorization.terminal_id,
            "terminalCreationStatus": request.terminal_creation_status,
            "channel": result.get("channel") or "terminal connected",
            "resumeMessage": (
                f"Terminal access approved for asset {request.asset_name}. "
                f"Use authorization_id {authorization.authorization_id} when executing commands on this asset."
            ),
        }

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
    ) -> dict[str, Any]:
        runtime = self._by_runtime.get(runtime_id)
        if runtime is None:
            raise ValueError("runtime not found")
        return self._append_runtime_event(
            runtime,
            "terminal_command_submitted",
            {
                "runtimeId": runtime_id,
                "authorizationId": authorization_id,
                "assetId": asset_id,
                "assetName": asset_name,
                "terminalId": terminal_id,
                "command": command,
                "approvalPolicy": approval_policy,
            },
        )

    def resolve_terminal_authorization(self, runtime_id: str, authorization_id: str) -> RuntimeTerminalAuthorization:
        runtime = self._by_runtime.get(runtime_id)
        if runtime is None:
            raise ValueError("runtime not found")
        self._expire_terminal_requests(runtime)
        authorization = runtime.terminal_authorizations.get(authorization_id)
        if authorization is None:
            for candidate in self._by_conversation.get(runtime.conversation_id, {}).values():
                self._expire_terminal_requests(candidate)
                authorization = candidate.terminal_authorizations.get(authorization_id)
                if authorization is not None:
                    break
        if authorization is None or authorization.status != "active":
            raise ValueError("terminal authorization is not active")
        return authorization

    def revoke_authorizations_for_terminal(
        self,
        terminal_id: str,
        *,
        status: TerminalAuthorizationStatus,
        reason: str,
    ) -> list[RuntimeTerminalAuthorization]:
        revoked: list[RuntimeTerminalAuthorization] = []
        for runtime in self._by_runtime.values():
            for authorization in runtime.terminal_authorizations.values():
                if authorization.terminal_id != terminal_id or authorization.status != "active":
                    continue
                now = self._now()
                authorization.status = status
                authorization.revoked_at = now
                authorization.updated_at = now
                authorization.revoke_reason = reason
                revoked.append(authorization)
                self.release_terminal_slot(runtime.runtime_id, terminal_id)
                self._append_runtime_event(
                    runtime,
                    "terminal_authorization_revoked",
                    {
                        "runtimeId": runtime.runtime_id,
                        "authorizationId": authorization.authorization_id,
                        "assetId": authorization.asset_id,
                        "assetName": authorization.asset_name,
                        "terminalId": authorization.terminal_id,
                        "status": authorization.status,
                        "reason": reason,
                        "revokeReason": reason,
                    },
                )
        return revoked

    def acquire_terminal_slot(self, runtime_id: str, terminal_id: str) -> bool:
        if terminal_id in self._terminal_slots and self._terminal_slots[terminal_id] != runtime_id:
            return False
        self._terminal_slots[terminal_id] = runtime_id
        return True

    def release_terminal_slot(self, runtime_id: str, terminal_id: str) -> None:
        if self._terminal_slots.get(terminal_id) == runtime_id:
            self._terminal_slots.pop(terminal_id, None)

    def cancel_runtime(self, runtime_id: str, *, reason: str = "Runtime cancelled.") -> dict[str, Any]:
        runtime = self._by_runtime.get(runtime_id)
        if runtime is None:
            raise ValueError("runtime not found")

        state = runtime.state
        state.cancel_requested = True
        state.error_message = reason
        if not state.is_terminal():
            state.phase = "cancelled"
        if state.pending_approval_step_id:
            step = state.get_step(state.pending_approval_step_id)
            if step is not None and step.status in {"pending", "running"}:
                step.status = "failed"
                step.output = reason
        state.pending_tool_call_id = None
        state.pending_tool_name = None
        state.pending_tool_args = None
        state.pending_message_id = None
        state.pending_approval_token = None
        state.pending_approval_token_hash = None
        state.pending_approval_consistency = None
        state.pending_approval_step_id = None

        now = self._now()
        for authorization in list(runtime.terminal_authorizations.values()):
            if authorization.status != "active":
                continue
            authorization.status = "revoked"
            authorization.revoked_at = now
            authorization.updated_at = now
            authorization.revoke_reason = reason
            self._append_runtime_event(
                runtime,
                "terminal_authorization_revoked",
                {
                    "runtimeId": runtime.runtime_id,
                    "authorizationId": authorization.authorization_id,
                    "assetId": authorization.asset_id,
                    "assetName": authorization.asset_name,
                    "terminalId": authorization.terminal_id,
                    "status": authorization.status,
                    "reason": reason,
                    "revokeReason": reason,
                },
            )

        return self._append_runtime_event(
            runtime,
            "cancelled",
            {
                "runtimeId": runtime_id,
                "status": state.phase,
                "error": reason,
                "text": reason,
            },
        )

    def create_runtime(self, *, conversation_id: str, asset_id: int, terminal_id: str | None, context: LoopContext) -> LoopState:
        self._expire_completed_runtimes()
        runtime_id = context.runtime_id
        state = LoopState(phase="executing", context=context)
        runtime = RuntimeState(
            runtime_id=runtime_id,
            conversation_id=conversation_id,
            asset_id=asset_id,
            terminal_id=terminal_id,
            state=state,
            events=deque(maxlen=2000),
            sequence=0,
            created_at=self._now(),
            updated_at=self._now(),
        )
        self._by_runtime[runtime_id] = runtime
        self._by_conversation.setdefault(conversation_id, {})[runtime_id] = runtime
        return state

    def get_runtime(self, runtime_id: str) -> RuntimeState | None:
        self._expire_completed_runtimes()
        return self._by_runtime.get(runtime_id)

    def list_runtimes(self, conversation_id: str) -> list[RuntimeState]:
        self._expire_completed_runtimes()
        return sorted(
            self._by_conversation.get(conversation_id, {}).values(),
            key=lambda runtime: runtime.updated_at,
            reverse=True,
        )

    def events_since(self, runtime_id: str, since: int) -> tuple[int, list[dict]]:
        self._expire_completed_runtimes()
        rt = self._by_runtime.get(runtime_id)
        if rt is None:
            raise ValueError("runtime not found")
        self._expire_terminal_requests(rt)
        events = [evt for evt in rt.events if int(evt.get("sequence", 0)) > since]
        return rt.sequence, events

    def get_snapshot(self, runtime_id: str) -> dict:
        self._expire_completed_runtimes()
        rt = self._by_runtime.get(runtime_id)
        if rt is None:
            raise ValueError("runtime not found")
        self._expire_terminal_requests(rt)
        state = rt.state
        current_step = state.get_current_step()
        return {
            "runtime_id": rt.runtime_id,
            "conversation_id": rt.conversation_id,
            "asset_id": rt.asset_id,
            "terminal_id": rt.terminal_id,
            "status": state.phase,
            "loaded_skill_name": state.context.loaded_skill_name,
            "mode": state.context.mode,
            "plan_version": state.plan_version,
            "locked_plan": state.locked_plan,
            "steps": [
                {
                    "step_id": s.step_id,
                    "title": s.title,
                    "command": "",
                    "reason": s.reason,
                    "risk_level": s.risk_level,
                    "working_directory": s.working_directory,
                    "expected_output": s.expected_output,
                    "status": s.status,
                    "output": s.output,
                    "exit_code": s.exit_code,
                }
                for s in state.steps
            ],
            "current_step_id": current_step.step_id if current_step else None,
            "pending_approval_step_id": state.pending_approval_step_id,
            "last_output_excerpt": state.last_output_excerpt,
            "summary": state.summary,
            "error_message": state.error_message,
            "pending_approval": self._pending_approval_view(state),
            "terminal_requests": [
                self._request_view(request, request.approval_token if request.user_decision_status == "pending" else None)
                for request in rt.terminal_requests.values()
            ],
            "terminal_authorizations": [
                self._authorization_view(authorization)
                for authorization in rt.terminal_authorizations.values()
                if authorization.status in {"active", "revoked", "closed", "expired", "replaced"}
            ],
            "created_at": rt.created_at,
            "updated_at": rt.updated_at,
            "last_sequence": rt.sequence,
        }

    def run(self, *, runtime_id: str, terminal_service) -> Iterator[dict]:
        rt = self._by_runtime.get(runtime_id)
        if rt is None:
            raise ValueError("runtime not found")

        loop = AgentLoop(tools=self._tools_factory(terminal_service), usage_callback=self._usage_callback)
        for event in loop.run(rt.state):
            yield self._to_ws_event(event, rt)
            usage_event = self._build_usage_event(rt)
            if usage_event is not None:
                yield usage_event

    def update_plan(self, *, runtime_id: str, steps: list[dict]) -> dict:
        rt = self._by_runtime.get(runtime_id)
        if rt is None:
            raise ValueError("runtime not found")
        state = rt.state
        if state.context.mode != "plan":
            raise ValueError("runtime is not in plan mode")
        if state.phase != "waiting_plan_approval" or state.locked_plan:
            raise ValueError("plan can only be edited before approval")
        if not steps:
            raise ValueError("plan must include at least one step")

        state.steps = [
            LoopRuntimeStep(
                step_id=str(item.get("id") or item.get("step_id") or f"step-{uuid.uuid4().hex[:8]}"),
                title=str(item.get("title") or "").strip() or f"Step {index}",
                reason=str(item.get("reason") or "Executing plan step"),
                risk_level=str(item.get("riskLevel") or item.get("risk_level") or "low"),
                working_directory=str(item.get("workingDirectory") or item.get("working_directory") or "") or None,
                expected_output=str(item.get("expectedOutput") or item.get("expected_output") or "") or None,
                status="pending",
            )
            for index, item in enumerate(steps, start=1)
        ]
        state.cursor = 0
        state.plan_version += 1
        rt.updated_at = self._now()
        return self._append_plan_event(rt)

    def approve_plan(self, *, runtime_id: str, terminal_service) -> Iterator[dict]:
        rt = self._by_runtime.get(runtime_id)
        if rt is None:
            raise ValueError("runtime not found")
        state = rt.state
        if state.context.mode != "plan":
            raise ValueError("runtime is not in plan mode")
        if state.phase != "waiting_plan_approval":
            raise ValueError("plan is not waiting for approval")
        if not state.steps:
            raise ValueError("plan has no steps")

        state.locked_plan = True
        state.cursor = 0
        state.phase = "executing"
        yield self._append_plan_event(rt)
        loop = AgentLoop(tools=self._tools_factory(terminal_service), usage_callback=self._usage_callback)
        for event in loop.run(rt.state):
            yield self._to_ws_event(event, rt)
            usage_event = self._build_usage_event(rt)
            if usage_event is not None:
                yield usage_event

    def _append_plan_event(self, rt: RuntimeState) -> dict:
        state = rt.state
        event = LoopEvent(
            event_type="plan",
            runtime_id=rt.runtime_id,
            phase=state.phase,
            payload={
                "planId": rt.runtime_id,
                "title": "Task Plan",
                "mode": state.context.mode,
                "version": state.plan_version,
                "lockedPlan": state.locked_plan,
                "status": state.phase,
                "steps": [
                    {
                        "id": step.step_id,
                        "title": step.title,
                        "command": "",
                        "reason": step.reason,
                        "riskLevel": step.risk_level,
                        "workingDirectory": step.working_directory,
                        "expectedOutput": step.expected_output,
                        "status": step.status,
                    }
                    for step in state.steps
                ],
            },
        )
        return self._to_ws_event(event, rt)

    def resume(
        self,
        *,
        runtime_id: str,
        approved: bool,
        approval_token: str | None,
        terminal_service,
        on_approval_validated: Callable[[], None] | None = None,
    ) -> Iterator[dict]:
        rt = self._by_runtime.get(runtime_id)
        if rt is None:
            raise ValueError("runtime not found")

        expected_token_hash = rt.state.pending_approval_token_hash
        if expected_token_hash is None:
            raise ValueError("approval token is not available")
        if approval_token is None or not secrets.compare_digest(
            expected_token_hash,
            hashlib.sha256(approval_token.encode("utf-8")).hexdigest(),
        ):
            raise PermissionError("invalid approval token")
        loop = AgentLoop(tools=self._tools_factory(terminal_service), usage_callback=self._usage_callback)
        for event in loop.resume_with_approval(
            rt.state,
            approved=approved,
            on_approval_validated=on_approval_validated,
        ):
            yield self._to_ws_event(event, rt)
            usage_event = self._build_usage_event(rt)
            if usage_event is not None:
                yield usage_event

    def resume_after_terminal_request(
        self,
        *,
        runtime_id: str,
        resume_message: str,
        terminal_service,
        authorization_id: str | None = None,
    ) -> Iterator[dict]:
        rt = self._by_runtime.get(runtime_id)
        if rt is None:
            raise ValueError("runtime not found")
        if rt.state.cancel_requested or rt.state.is_terminal():
            raise ValueError("runtime is already terminal")
        rt.state.phase = "executing"
        self._set_default_authorization_context(
            rt,
            authorization_id or self._latest_active_authorization_id(rt) or rt.state.context.default_authorization_id,
        )
        rt.state.messages.append(LLMMessage(role="user", content=self._terminal_request_resume_prompt(rt, resume_message)))
        loop = AgentLoop(tools=self._tools_factory(terminal_service), usage_callback=self._usage_callback)
        for event in loop.run(rt.state):
            yield self._to_ws_event(event, rt)
            usage_event = self._build_usage_event(rt)
            if usage_event is not None:
                yield usage_event

    def _terminal_request_resume_prompt(self, rt: RuntimeState, resume_message: str) -> str:
        active_authorizations = [
            authorization
            for authorization in rt.terminal_authorizations.values()
            if authorization.status == "active"
        ]
        authorization_lines = []
        for authorization in active_authorizations:
            authorization_lines.append(
                "\n".join(
                    [
                        f"- {authorization.asset_name} (asset_id={authorization.asset_id}) authorization_id={authorization.authorization_id}",
                        f"  terminal_id: {authorization.terminal_id}",
                        f"  Asset Type: {authorization.asset_type or 'unknown'}",
                        f"  Shell: {authorization.shell_type}",
                        f"  Operating System Type: {authorization.os_type}",
                        f"  Execution Profile: {authorization.execution_profile}",
                        f"  Device Vendor: {authorization.device_vendor or 'unknown'}",
                        f"  Current Host Information: {authorization.asset_summary}",
                        f"  Device Execution Rules:\n{authorization.device_context}" if authorization.device_context else "  Device Execution Rules: none",
                    ]
                )
            )
        authorization_summary = "\n".join(authorization_lines) if authorization_lines else "- None"
        return (
            f"Terminal request result: {resume_message}\n\n"
            f"Original task: {rt.state.context.user_prompt}\n\n"
            "Active terminal authorizations for this runtime:\n"
            f"{authorization_summary}\n\n"
            "Continue the original task. If the user requested additional assets that are not listed above, "
            "request terminal access for those assets before executing commands or producing the final summary. "
            "Use execute_command with the matching authorization_id and terminal_id for each authorized asset."
        )

    def _latest_active_authorization_id(self, rt: RuntimeState) -> str | None:
        active_authorizations = [
            authorization
            for authorization in rt.terminal_authorizations.values()
            if authorization.status == "active"
        ]
        if not active_authorizations:
            return None
        latest_authorization = max(active_authorizations, key=lambda authorization: authorization.created_at)
        return latest_authorization.authorization_id

    def _set_default_authorization_context(self, rt: RuntimeState, authorization_id: str | None) -> None:
        if not authorization_id:
            return
        authorization = rt.terminal_authorizations.get(authorization_id)
        if authorization is None or authorization.status != "active":
            return
        context = rt.state.context
        context.default_authorization_id = authorization.authorization_id
        context.asset_id = authorization.asset_id
        context.asset_type = authorization.asset_type
        context.terminal_id = authorization.terminal_id
        context.asset_summary = authorization.asset_summary
        context.shell_type = authorization.shell_type
        context.os_type = authorization.os_type
        context.execution_profile = authorization.execution_profile
        context.device_vendor = authorization.device_vendor
        context.device_context = authorization.device_context

    def _pending_approval_view(self, state: LoopState) -> dict[str, Any] | None:
        if state.phase != "approving" or state.pending_approval_token is None:
            return None
        args = dict(state.pending_tool_args or {})
        return {
            "runtimeId": state.context.runtime_id,
            "stepId": state.pending_approval_step_id,
            "messageId": state.pending_message_id,
            "toolCallId": state.pending_tool_call_id,
            "toolName": state.pending_tool_name,
            "approvalToken": state.pending_approval_token,
            "command": str(args.get("command", "") or ""),
            "args": args,
        }

    def _context_percent_for_tokens(self, token_count: int, model_config) -> int:
        model_name = model_config.model_name.lower()
        if "claude" in model_name:
            context_window_tokens = 200_000
        elif "gpt-4" in model_name or "gpt-5" in model_name:
            context_window_tokens = 128_000
        else:
            context_window_tokens = 32_000
        available_tokens = max(1, context_window_tokens - 4_000)
        return min(100, max(0, round(token_count * 100 / available_tokens)))

    def _context_status_for_percent(self, context_percent: int) -> Literal["normal", "warning", "critical"]:
        if context_percent >= 90:
            return "critical"
        if context_percent >= 70:
            return "warning"
        return "normal"

    def _build_usage_event(self, rt: RuntimeState) -> dict | None:
        state = rt.state
        if self._usage_callback is None:
            return None
        usage = getattr(state, "latest_usage", None)
        if usage is None:
            return None
        context_percent = self._context_percent_for_tokens(int(usage.get("totalTokens") or 0), state.context.model_config)
        state.latest_usage = None
        rt.sequence += 1
        rt.updated_at = self._now()
        event = {
            "id": f"evt-context-{uuid.uuid4().hex[:12]}",
            "kind": "context_status",
            "runtimeId": rt.runtime_id,
            "sequence": rt.sequence,
            "ts": self._now().isoformat(),
            "contextPercent": context_percent,
            "contextStatus": self._context_status_for_percent(context_percent),
            "tokenUsage": usage,
        }
        rt.events.append(event)
        return event

    def _to_ws_event(self, event: LoopEvent, rt: RuntimeState) -> dict:
        rt.sequence += 1
        rt.updated_at = self._now()
        kind = event.event_type.replace("loop_", "")
        
        if kind == "message_update":
            # For message_update events, use the message's own id and spread
            # all message fields at the top level for the frontend to consume.
            ws_event = {
                **event.payload,           # id, ts, type, text, partial, toolCall, etc.
                "kind": kind,              # Override kind to "message_update" for transport
                "runtimeId": event.runtime_id,
                "sequence": rt.sequence,
            }
        else:
            ws_event = {
                "id": f"evt-{uuid.uuid4().hex[:12]}",
                "kind": kind,
                "runtimeId": event.runtime_id,
                "sequence": rt.sequence,
                "ts": self._now().isoformat(),
                **event.payload,
            }
        
        if event.message_id:
            ws_event["messageId"] = event.message_id
        if event.stage:
            ws_event["stage"] = event.stage
        if event.step_id:
            ws_event["stepId"] = event.step_id

        stored_event = dict(ws_event)
        tool_call = stored_event.get("toolCall")
        if isinstance(tool_call, dict) and "approvalToken" in tool_call:
            stored_event["toolCall"] = {**tool_call, "approvalToken": None}
        rt.events.append(stored_event)
        return ws_event

def new_runtime_id() -> str:
    return str(uuid.uuid4())
