from __future__ import annotations

import hashlib
import secrets
import threading
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.connectors.device_profiles import select_device_profile, select_execution_profile
from app.core.connectors.execution_context import build_asset_summary, build_device_context, infer_os_type
from app.core.loop.loop_state import LoopContext
from app.core.loop.runtime_execution import RuntimeExecutionMixin
from app.core.loop.runtime_persistence import RuntimePersistenceMixin
from app.core.loop.runtime_models import (
    PendingTerminalRequest,
    RuntimeState,
    RuntimeTerminalAuthorization,
    TerminalAuthorizationStatus,
)
from app.services.runtime_store import RuntimeStore


class LoopRuntimeManager(RuntimeExecutionMixin, RuntimePersistenceMixin):
    COMPLETED_RUNTIME_TTL = timedelta(minutes=30)

    def __init__(self, *, tools_factory, usage_callback=None):
        self._tools_factory = tools_factory
        self._usage_callback = usage_callback
        self._by_runtime: dict[str, RuntimeState] = {}
        self._by_conversation: dict[str, dict[str, RuntimeState]] = {}
        self._terminal_slots: dict[str, str] = {}
        self._state_lock = threading.RLock()
        self._runtime_store = RuntimeStore()

    def _now(self) -> datetime:
        return datetime.now(UTC)

    def _hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _expire_completed_runtimes(self) -> None:
        now = self._now()
        expired_runtime_ids = [
            runtime_id
            for runtime_id, runtime in self._by_runtime.items()
            if runtime.state.phase in {"completed", "failed"}
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
    ) -> dict[str, Any]:
        return {
            "status": request.user_decision_status,
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
        with self._state_lock:
            if terminal_id in self._terminal_slots and self._terminal_slots[terminal_id] != runtime_id:
                return False
            self._terminal_slots[terminal_id] = runtime_id
            return True

    def release_terminal_slot(self, runtime_id: str, terminal_id: str) -> None:
        with self._state_lock:
            if self._terminal_slots.get(terminal_id) == runtime_id:
                self._terminal_slots.pop(terminal_id, None)

def new_runtime_id() -> str:
    return str(uuid.uuid4())
