from __future__ import annotations

import logging
import queue
import hashlib
import secrets
import threading
import uuid
from collections import Counter
from collections import deque
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlmodel import Session

from app.db.repositories.assets import get_asset, list_assets
from app.db.repositories.models import get_default_model_config
from app.services.console_app_service import ConsoleAppService
from app.services.model_service import ModelService
from app.services.target_asset_resolver import (
    TargetAssetResolver,
    TargetAssetSelection,
    candidate_from_asset,
)
from app.services.terminal_service import TerminalService


logger = logging.getLogger(__name__)


OrchestrationStatus = Literal[
    "running",
    "needs_approval",
    "completed",
    "partial_failed",
    "failed",
    "cancelled",
]
ChildRunStatus = Literal[
    "pending",
    "running",
    "needs_approval",
    "completed",
    "failed",
    "cancelled",
]
PreparationStatus = Literal["ready", "needs_terminal", "unavailable"]


class OrchestrationStateConflict(ValueError):
    pass


class OrchestrationPermissionDenied(PermissionError):
    pass


@dataclass
class TargetPreparation:
    asset_id: int
    asset_name: str
    status: PreparationStatus
    terminal_id: str | None = None
    reason: str = ""


@dataclass
class OrchestrationTargetPreview:
    confirmation_token: str
    prompt: str
    conversation_id: str
    current_asset_id: int | None
    model_name: str | None
    target_asset_ids: list[int]
    target_selection_source: str
    target_selection_reason: str
    target_selection_confidence: str
    preparations: list[TargetPreparation]
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC) + timedelta(minutes=5))


@dataclass
class ChildRunState:
    asset_id: int
    asset_name: str
    prepared_terminal_id: str | None = None
    preparation_status: PreparationStatus = "needs_terminal"
    runtime_id: str | None = None
    terminal_id: str | None = None
    status: ChildRunStatus = "pending"
    summary: str = ""
    error_message: str = ""
    last_sequence: int = 0


@dataclass
class OrchestrationState:
    orchestration_id: str
    conversation_id: str
    prompt: str
    target_asset_ids: list[int]
    target_selection_source: str
    target_selection_reason: str
    target_selection_confidence: str
    model_name: str | None
    selected_skill_name: str | None
    max_concurrency: int
    status: OrchestrationStatus
    children: dict[int, ChildRunState]
    events: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=4000))
    sequence: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    final_summary: str | None = None
    cancelled: bool = False


class OrchestrationService:
    def __init__(
        self,
        *,
        console_service: ConsoleAppService,
        target_resolver: TargetAssetResolver | None = None,
        model_service: ModelService | None = None,
        max_workers_cap: int = 10,
    ) -> None:
        self._console_service = console_service
        self._target_resolver = target_resolver or TargetAssetResolver()
        self._model_service = model_service or ModelService()
        self._max_workers_cap = max_workers_cap
        self._by_id: dict[str, OrchestrationState] = {}
        self._target_previews: dict[str, OrchestrationTargetPreview] = {}
        self._lock = threading.RLock()

    def resolve_targets(
        self,
        *,
        session: Session,
        prompt: str,
        current_asset_id: int | None,
        model_name: str | None,
        explicit_asset_ids: list[int] | None = None,
    ) -> TargetAssetSelection:
        assets = list_assets(session)
        candidates = [
            candidate
            for asset in assets
            if (candidate := candidate_from_asset(asset)) is not None
        ]
        selection = self._target_resolver.resolve(
            prompt=prompt,
            current_asset_id=current_asset_id,
            candidates=candidates,
            model_config=None,
            explicit_asset_ids=explicit_asset_ids,
        )
        if selection.source == "llm_unavailable_default":
            model_config = self._resolve_model_config(session, model_name)
            selection = self._target_resolver.resolve(
                prompt=prompt,
                current_asset_id=current_asset_id,
                candidates=candidates,
                model_config=model_config,
                explicit_asset_ids=explicit_asset_ids,
            )
        if not selection.asset_ids:
            raise ValueError(selection.reason)
        valid_ids = {candidate.id for candidate in candidates}
        invalid_ids = [asset_id for asset_id in selection.asset_ids if asset_id not in valid_ids]
        if invalid_ids:
            raise ValueError(f"Target assets are not valid: {invalid_ids}")
        return selection

    def prepare_targets(
        self,
        *,
        session: Session,
        terminal_service: TerminalService,
        prompt: str,
        conversation_id: str,
        current_asset_id: int | None,
        model_name: str | None,
        explicit_asset_ids: list[int] | None = None,
    ) -> tuple[TargetAssetSelection, list[TargetPreparation], str]:
        selection = self.resolve_targets(
            session=session,
            prompt=prompt,
            current_asset_id=current_asset_id,
            model_name=model_name,
            explicit_asset_ids=explicit_asset_ids,
        )
        preparations: list[TargetPreparation] = []
        for asset_id in selection.asset_ids:
            asset = get_asset(session, asset_id)
            if asset is None or asset.id is None:
                preparations.append(
                    TargetPreparation(
                        asset_id=asset_id,
                        asset_name=f"asset-{asset_id}",
                        status="unavailable",
                        reason=f"Asset not found: {asset_id}",
                    )
                )
                continue

            terminal_id = terminal_service.find_session_id(f"asset:{asset.id}")
            if terminal_id:
                preparations.append(
                    TargetPreparation(
                        asset_id=asset.id,
                        asset_name=asset.name,
                        status="ready",
                        terminal_id=terminal_id,
                        reason="Existing terminal session is ready.",
                    )
                )
                continue

            preparations.append(
                TargetPreparation(
                    asset_id=asset.id,
                    asset_name=asset.name,
                    status="needs_terminal",
                    reason="Terminal session will be opened when the run starts.",
                )
            )
        token = secrets.token_urlsafe(32)
        preview = OrchestrationTargetPreview(
            confirmation_token=token,
            prompt=prompt,
            conversation_id=conversation_id,
            current_asset_id=current_asset_id,
            model_name=model_name,
            target_asset_ids=list(selection.asset_ids),
            target_selection_source=selection.source,
            target_selection_reason=selection.reason,
            target_selection_confidence=selection.confidence,
            preparations=preparations,
        )
        with self._lock:
            self._expire_target_previews_locked()
            self._target_previews[token] = preview
        return selection, preparations, token

    def _expire_target_previews_locked(self) -> None:
        now = datetime.now(UTC)
        expired_tokens = [
            token
            for token, preview in self._target_previews.items()
            if preview.expires_at <= now
        ]
        for token in expired_tokens:
            self._target_previews.pop(token, None)

    def _consume_target_preview(
        self,
        *,
        confirmation_token: str | None,
        prompt: str,
        conversation_id: str,
        current_asset_id: int | None,
        model_name: str | None,
        target_asset_ids: list[int] | None,
    ) -> OrchestrationTargetPreview:
        if not confirmation_token:
            raise ValueError("Multi-asset run requires target preflight confirmation.")
        with self._lock:
            self._expire_target_previews_locked()
            preview = self._target_previews.get(confirmation_token)
            if preview is None:
                raise ValueError("Target preflight confirmation is missing or expired.")
            requested_asset_ids = target_asset_ids or preview.target_asset_ids
            if (
                preview.prompt != prompt
                or preview.conversation_id != conversation_id
                or preview.current_asset_id != current_asset_id
                or preview.model_name != model_name
                or Counter(preview.target_asset_ids) != Counter(requested_asset_ids)
            ):
                raise ValueError("Target preflight confirmation does not match the requested run.")
            self._target_previews.pop(confirmation_token, None)
        return preview

    def _ensure_child_terminal(self, *, child: ChildRunState, session: Session, terminal_service: TerminalService) -> None:
        if child.prepared_terminal_id:
            if terminal_service.session_belongs_to_asset(child.prepared_terminal_id, child.asset_id):
                child.terminal_id = child.prepared_terminal_id
                child.preparation_status = "ready"
                return
            child.prepared_terminal_id = None
            child.terminal_id = None
            child.preparation_status = "needs_terminal"
        asset = get_asset(session, child.asset_id)
        if asset is None or asset.id is None:
            raise ValueError(f"Asset not found: {child.asset_id}")
        result = terminal_service.open_session(asset, reuse_existing=True)
        terminal_id = result.get("terminal_id")
        if not terminal_id:
            raise ValueError(str(result.get("error") or "Terminal session could not be opened."))
        child.prepared_terminal_id = str(terminal_id)
        child.terminal_id = str(terminal_id)
        child.preparation_status = "ready"

    def stream_run(
        self,
        *,
        session: Session,
        terminal_service: TerminalService,
        prompt: str,
        current_asset_id: int | None,
        target_asset_ids: list[int] | None,
        conversation_id: str,
        model_name: str | None,
        selected_skill_name: str | None,
        max_concurrency: int,
        confirmation_token: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        preview = self._consume_target_preview(
            confirmation_token=confirmation_token,
            prompt=prompt,
            conversation_id=conversation_id,
            current_asset_id=current_asset_id,
            model_name=model_name,
            target_asset_ids=target_asset_ids,
        )
        preparations = preview.preparations

        children: dict[int, ChildRunState] = {}
        for preparation in preparations:
            prepared_terminal_id = preparation.terminal_id
            preparation_status = preparation.status
            preparation_reason = preparation.reason
            if prepared_terminal_id and not terminal_service.session_belongs_to_asset(prepared_terminal_id, preparation.asset_id):
                prepared_terminal_id = None
                preparation_status = "needs_terminal"
                preparation_reason = "Previously prepared terminal is no longer available; a new terminal session will be opened when the run starts."
            children[preparation.asset_id] = ChildRunState(
                asset_id=preparation.asset_id,
                asset_name=preparation.asset_name,
                prepared_terminal_id=prepared_terminal_id,
                preparation_status=preparation_status,
                terminal_id=prepared_terminal_id,
                status="failed" if preparation_status == "unavailable" else "pending",
                error_message=preparation_reason if preparation_status == "unavailable" else "",
            )

        orchestration = OrchestrationState(
            orchestration_id=f"orch-{uuid.uuid4().hex}",
            conversation_id=conversation_id,
            prompt=prompt,
            target_asset_ids=list(children.keys()),
            target_selection_source=preview.target_selection_source,
            target_selection_reason=preview.target_selection_reason,
            target_selection_confidence=preview.target_selection_confidence,
            model_name=model_name,
            selected_skill_name=selected_skill_name,
            max_concurrency=max(1, min(max_concurrency, self._max_workers_cap)),
            status="running",
            children=children,
        )
        with self._lock:
            self._by_id[orchestration.orchestration_id] = orchestration

        yield self._append_event(
            orchestration,
            "orchestration_started",
            {
                "orchestrationId": orchestration.orchestration_id,
                "conversationId": conversation_id,
                "targetAssetIds": orchestration.target_asset_ids,
                "targetSelectionSource": orchestration.target_selection_source,
                "targetSelectionReason": orchestration.target_selection_reason,
                "confidence": orchestration.target_selection_confidence,
                "maxConcurrency": orchestration.max_concurrency,
                "children": [self._child_view(child) for child in orchestration.children.values()],
            },
        )

        event_queue: queue.Queue[dict[str, Any] | None] = queue.Queue()
        runnable_children = [child for child in orchestration.children.values() if child.status == "pending"]
        remaining = len(runnable_children)

        for child in orchestration.children.values():
            if child.status != "failed":
                continue
            yield self._append_event(
                orchestration,
                "child_runtime_failed",
                {
                    "orchestrationId": orchestration.orchestration_id,
                    "assetId": child.asset_id,
                    "assetName": child.asset_name,
                    "status": child.status,
                    "errorMessage": child.error_message,
                },
            )

        if remaining == 0:
            yield self._finalize(orchestration)
            yield self._append_event(
                orchestration,
                "orchestration_failed",
                {
                    "orchestrationId": orchestration.orchestration_id,
                    "status": orchestration.status,
                    "finalSummary": orchestration.final_summary,
                },
            )
            return

        executor = ThreadPoolExecutor(max_workers=orchestration.max_concurrency)
        try:
            for child in runnable_children:
                executor.submit(
                    self._run_child,
                    orchestration,
                    child,
                    terminal_service,
                    prompt,
                    model_name,
                    selected_skill_name,
                    event_queue,
                )

            while remaining > 0:
                if orchestration.cancelled:
                    for child in runnable_children:
                        if child.status in {"completed", "failed", "cancelled"}:
                            continue
                        child.status = "cancelled"
                        yield self._append_event(
                            orchestration,
                            "child_runtime_status",
                            {
                                "orchestrationId": orchestration.orchestration_id,
                                "runtimeId": child.runtime_id,
                                "assetId": child.asset_id,
                                "assetName": child.asset_name,
                                "terminalId": child.terminal_id,
                                "status": child.status,
                                "summary": child.summary,
                                "errorMessage": child.error_message,
                            },
                        )
                    executor.shutdown(wait=False, cancel_futures=True)
                    yield self._finalize(orchestration)
                    yield self._append_event(
                        orchestration,
                        "orchestration_cancelled",
                        {
                            "orchestrationId": orchestration.orchestration_id,
                            "status": orchestration.status,
                            "finalSummary": orchestration.final_summary,
                        },
                    )
                    return
                try:
                    item = event_queue.get(timeout=0.2)
                except queue.Empty:
                    continue
                if item is None:
                    remaining -= 1
                    continue
                yield item
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        yield self._finalize(orchestration)
        yield self._append_event(
            orchestration,
            self._terminal_event_kind(orchestration),
            {
                "orchestrationId": orchestration.orchestration_id,
                "status": orchestration.status,
                "finalSummary": orchestration.final_summary,
            },
        )

    def get_snapshot(self, orchestration_id: str) -> dict[str, Any]:
        return self._snapshot(self._get(orchestration_id))

    def events_since(self, orchestration_id: str, since: int) -> tuple[int, list[dict[str, Any]]]:
        orchestration = self._get(orchestration_id)
        events = [event for event in orchestration.events if int(event.get("sequence", 0)) > since]
        return orchestration.sequence, events

    def cancel(self, orchestration_id: str) -> dict[str, Any]:
        orchestration = self._get(orchestration_id)
        orchestration.cancelled = True
        orchestration.status = "cancelled"
        for child in orchestration.children.values():
            if child.runtime_id:
                try:
                    self._console_service.cancel_runtime(
                        child.runtime_id,
                        reason=f"Orchestration {orchestration_id} was cancelled.",
                    )
                except ValueError:
                    logger.warning(
                        "orchestration child runtime was not available during cancel: orchestration_id=%s runtime_id=%s",
                        orchestration_id,
                        child.runtime_id,
                    )
            if child.status in {"pending", "running", "needs_approval"}:
                child.status = "cancelled"
        self._finalize(orchestration)
        return self._append_event(
            orchestration,
            "orchestration_cancelled",
            {
                "orchestrationId": orchestration_id,
                "status": "cancelled",
                "finalSummary": orchestration.final_summary,
                "children": [self._child_view(child) for child in orchestration.children.values()],
            },
        )

    def _run_child(
        self,
        orchestration: OrchestrationState,
        child: ChildRunState,
        terminal_service: TerminalService,
        prompt: str,
        model_name: str | None,
        selected_skill_name: str | None,
        event_queue: queue.Queue[dict[str, Any] | None],
    ) -> None:
        if orchestration.cancelled:
            child.status = "cancelled"
            event_queue.put(None)
            return

        child.status = "running"
        child_prompt = self._child_prompt(
            prompt=prompt,
            asset_id=child.asset_id,
            asset_name=child.asset_name,
        )
        event_queue.put(
            self._append_event(
                orchestration,
                "child_runtime_started",
                {
                    "orchestrationId": orchestration.orchestration_id,
                    "assetId": child.asset_id,
                    "assetName": child.asset_name,
                    "terminalId": child.terminal_id,
                    "status": child.status,
                },
            )
        )

        try:
            from app.db.session import Session as DbSession
            from app.db.session import engine

            with DbSession(engine) as child_session:
                self._ensure_child_terminal(child=child, session=child_session, terminal_service=terminal_service)
                if orchestration.cancelled:
                    child.status = "cancelled"
                    return
                event_queue.put(
                    self._append_event(
                        orchestration,
                        "child_runtime_status",
                        {
                            "orchestrationId": orchestration.orchestration_id,
                            "assetId": child.asset_id,
                            "assetName": child.asset_name,
                            "terminalId": child.terminal_id,
                            "status": child.status,
                            "errorMessage": "",
                        },
                    )
                )
                stream = self._console_service.stream_run(
                    session=child_session,
                    prompt=child_prompt,
                    asset_id=child.asset_id,
                    terminal_id=child.terminal_id,
                    model_name=model_name,
                    selected_skill_name=selected_skill_name,
                    conversation_id=orchestration.conversation_id,
                    mode="agent",
                    terminal_service=terminal_service,
                )
                for event in stream:
                    if orchestration.cancelled:
                        child.status = "cancelled"
                        break
                    self._apply_child_runtime_event(orchestration, child, event)
                    event_queue.put(
                        self._append_event(
                            orchestration,
                            "child_runtime_event",
                            {
                                "orchestrationId": orchestration.orchestration_id,
                                "runtimeId": child.runtime_id,
                                "assetId": child.asset_id,
                                "assetName": child.asset_name,
                                "terminalId": child.terminal_id,
                                "childSequence": child.last_sequence,
                                "event": event,
                            },
                        )
                    )
            if child.status not in {"failed", "cancelled", "needs_approval"}:
                child.status = "completed"
        except Exception as exc:
            child.status = "failed"
            child.error_message = str(exc)
            event_queue.put(
                self._append_event(
                    orchestration,
                    "child_runtime_failed",
                    {
                        "orchestrationId": orchestration.orchestration_id,
                        "runtimeId": child.runtime_id,
                        "assetId": child.asset_id,
                        "assetName": child.asset_name,
                        "terminalId": child.terminal_id,
                        "errorMessage": child.error_message,
                    },
                )
            )
        finally:
            terminal_kind = "child_runtime_status"
            if child.status == "completed":
                terminal_kind = "child_runtime_completed"
            elif child.status == "failed":
                terminal_kind = "child_runtime_failed"
            event_queue.put(
                self._append_event(
                    orchestration,
                    terminal_kind,
                    {
                        "orchestrationId": orchestration.orchestration_id,
                        "runtimeId": child.runtime_id,
                        "assetId": child.asset_id,
                        "assetName": child.asset_name,
                        "terminalId": child.terminal_id,
                        "status": child.status,
                        "summary": child.summary,
                        "errorMessage": child.error_message,
                    },
                )
            )
            event_queue.put(None)

    def _terminal_event_kind(self, orchestration: OrchestrationState) -> str:
        if orchestration.status == "needs_approval":
            return "orchestration_needs_approval"
        if orchestration.status in {"completed", "partial_failed"}:
            return "orchestration_completed"
        if orchestration.status == "cancelled":
            return "orchestration_cancelled"
        return "orchestration_failed"

    def stream_child_approval(
        self,
        *,
        session: Session,
        orchestration_id: str,
        runtime_id: str,
        approved: bool,
        approval_token: str | None,
        allow_prefix: str | None,
        terminal_service: TerminalService,
    ) -> Iterator[dict[str, Any]]:
        self.validate_child_approval_request(
            orchestration_id=orchestration_id,
            runtime_id=runtime_id,
            approval_token=approval_token,
        )
        orchestration = self._get(orchestration_id)
        child = self._child_for_runtime(orchestration, runtime_id)
        stream = self._console_service.stream_approve(
            session=session,
            runtime_id=runtime_id,
            approved=approved,
            approval_token=approval_token,
            allow_prefix=allow_prefix,
            terminal_service=terminal_service,
        )
        pending_approval_after_resume = False
        approval_resume_failed = False
        rejected_by_user = not approved
        for event in stream:
            event_kind = str(event.get("kind") or "")
            if event_kind == "error" and event.get("recoverable") is True and child.status == "needs_approval":
                approval_resume_failed = True
                child.error_message = str(event.get("error") or event.get("text") or "Approval resume failed.")
                yield self._append_event(
                    orchestration,
                    "child_runtime_event",
                    {
                        "orchestrationId": orchestration.orchestration_id,
                        "runtimeId": child.runtime_id,
                        "assetId": child.asset_id,
                        "assetName": child.asset_name,
                        "terminalId": child.terminal_id,
                        "childSequence": child.last_sequence,
                        "event": event,
                    },
                )
                continue
            self._apply_child_runtime_event(orchestration, child, event)
            if event_kind == "message_update" and event.get("type") == "ask":
                raw_tool_call = event.get("toolCall")
                tool_call: dict[str, Any] = raw_tool_call if isinstance(raw_tool_call, dict) else {}
                next_approval_token = tool_call.get("approvalToken")
                pending_approval_after_resume = bool(next_approval_token and next_approval_token != approval_token)
            elif event_kind in {"approval_decision", "approval_granted"}:
                pending_approval_after_resume = False
            yield self._append_event(
                orchestration,
                "child_runtime_event",
                {
                    "orchestrationId": orchestration.orchestration_id,
                    "runtimeId": child.runtime_id,
                    "assetId": child.asset_id,
                    "assetName": child.asset_name,
                    "terminalId": child.terminal_id,
                    "childSequence": child.last_sequence,
                    "event": event,
                },
            )
        if approval_resume_failed:
            child.status = "needs_approval"
            orchestration.status = "needs_approval"
            yield self._append_event(
                orchestration,
                "child_runtime_status",
                {
                    "orchestrationId": orchestration.orchestration_id,
                    "runtimeId": child.runtime_id,
                    "assetId": child.asset_id,
                    "assetName": child.asset_name,
                    "terminalId": child.terminal_id,
                    "status": child.status,
                    "summary": child.summary,
                    "errorMessage": child.error_message,
                },
            )
            return
        if rejected_by_user and child.status != "cancelled":
            child.status = "failed"
            child.error_message = "Approval rejected."
        if child.status not in {"failed", "cancelled"} and not pending_approval_after_resume:
            child.status = "completed"
        terminal_kind = "child_runtime_status"
        if child.status == "completed":
            terminal_kind = "child_runtime_completed"
        elif child.status == "failed":
            terminal_kind = "child_runtime_failed"
        yield self._append_event(
            orchestration,
            terminal_kind,
            {
                "orchestrationId": orchestration.orchestration_id,
                "runtimeId": child.runtime_id,
                "assetId": child.asset_id,
                "assetName": child.asset_name,
                "terminalId": child.terminal_id,
                "status": child.status,
                "summary": child.summary,
                "errorMessage": child.error_message,
            },
        )
        if any(item.status in {"pending", "running"} for item in orchestration.children.values()):
            return
        yield self._finalize(orchestration)
        yield self._append_event(
            orchestration,
            self._terminal_event_kind(orchestration),
            {
                "orchestrationId": orchestration.orchestration_id,
                "status": orchestration.status,
                "finalSummary": orchestration.final_summary,
            },
        )

    def validate_child_approval_request(
        self,
        *,
        orchestration_id: str,
        runtime_id: str,
        approval_token: str | None,
    ) -> None:
        orchestration = self._get(orchestration_id)
        child = self._child_for_runtime(orchestration, runtime_id)
        if orchestration.cancelled or orchestration.status == "cancelled":
            raise OrchestrationStateConflict("orchestration is cancelled")
        if child.status != "needs_approval":
            raise OrchestrationStateConflict(f"orchestration child is not waiting for approval: {child.status}")
        runtime = self._console_service.runtime_manager.get_runtime(runtime_id)
        if runtime is None:
            raise ValueError("runtime not found")
        state = runtime.state
        if state.cancel_requested or state.is_terminal():
            raise OrchestrationStateConflict("runtime is already terminal")
        if state.phase != "approving":
            raise OrchestrationStateConflict("runtime is not waiting for approval")
        expected_token_hash = state.pending_approval_token_hash
        if expected_token_hash is None:
            raise OrchestrationStateConflict("approval token is not available")
        if approval_token is None or not secrets.compare_digest(
            expected_token_hash,
            hashlib.sha256(approval_token.encode("utf-8")).hexdigest(),
        ):
            raise OrchestrationPermissionDenied("invalid approval token")

    def _child_prompt(self, *, prompt: str, asset_id: int, asset_name: str) -> str:
        return (
            "你是多资产任务中的一个子任务执行者。\n"
            f"总任务：{prompt}\n"
            f"当前目标资产：{asset_name} (asset_id={asset_id})\n\n"
            "只在当前资产上执行必要检查。不要请求其他资产的终端访问。\n"
            "完成后给出结构化摘要：执行了什么、关键输出、是否成功、异常或建议。"
        )

    def _apply_child_runtime_event(
        self,
        orchestration: OrchestrationState,
        child: ChildRunState,
        event: dict[str, Any],
    ) -> None:
        with self._lock:
            runtime_id = str(event.get("runtimeId") or "")
            if runtime_id and child.runtime_id is None:
                child.runtime_id = runtime_id
            terminal_id = event.get("terminalId") or event.get("terminal_id")
            if isinstance(terminal_id, str) and terminal_id:
                child.terminal_id = terminal_id
            child.last_sequence = int(event.get("sequence") or child.last_sequence or 0)
            kind = str(event.get("kind") or "")
            if kind == "message_update" and event.get("type") == "ask":
                child.status = "needs_approval"
                orchestration.status = "needs_approval"
            if kind == "message_update" and event.get("type") == "say" and not event.get("partial"):
                child.summary = str(event.get("text") or child.summary or "")
            if kind == "message_update" and event.get("type") == "say":
                exit_code = self._event_exit_code(event)
                if isinstance(exit_code, int) and exit_code != 0:
                    child.status = "failed"
                    child.error_message = f"Command exited with status {exit_code}."
            if kind in {"approval_decision", "approval_granted"}:
                child.status = "running"
                if orchestration.status == "needs_approval":
                    orchestration.status = "running"
            if kind == "approval_rejected":
                child.status = "failed"
                child.error_message = "Approval rejected."
            if kind in {"command_end", "execution_completed"}:
                failure_reason = self._event_failure_reason(event)
                if failure_reason:
                    child.status = "failed"
                    child.error_message = failure_reason
            if kind in {"completed", "final", "loop_final"} and child.status != "failed":
                child.status = "completed"
                child.summary = str(event.get("summary") or event.get("text") or "")
            if kind in {"failed", "error", "loop_failed", "task_failed"}:
                child.status = "failed"
                child.error_message = str(event.get("error") or event.get("text") or "Child runtime failed.")

    def _event_exit_code(self, event: dict[str, Any]) -> int | None:
        exit_code = event.get("exitCode") if event.get("exitCode") is not None else event.get("exit_code")
        return exit_code if isinstance(exit_code, int) else None

    def _event_failure_reason(self, event: dict[str, Any]) -> str:
        exit_code = self._event_exit_code(event)
        if isinstance(exit_code, int) and exit_code != 0:
            return f"Command exited with status {exit_code}."
        completed = event.get("completed")
        success = event.get("success")
        needs_attention = event.get("needsAttention") if event.get("needsAttention") is not None else event.get("needs_attention")
        if completed is False or success is False or needs_attention is True:
            completion_reason = str(event.get("completionReason") or event.get("completion_reason") or "command did not complete successfully")
            return f"Command did not complete successfully: {completion_reason}."
        return ""

    def _finalize(self, orchestration: OrchestrationState) -> dict[str, Any]:
        completed = [child for child in orchestration.children.values() if child.status == "completed"]
        failed = [child for child in orchestration.children.values() if child.status == "failed"]
        needs_approval = [child for child in orchestration.children.values() if child.status == "needs_approval"]
        cancelled = [child for child in orchestration.children.values() if child.status == "cancelled"]
        if orchestration.cancelled or orchestration.status == "cancelled":
            orchestration.status = "cancelled"
        elif needs_approval:
            orchestration.status = "needs_approval"
        elif completed and failed:
            orchestration.status = "partial_failed"
        elif failed and not completed:
            orchestration.status = "failed"
        elif any(child.status in {"pending", "running"} for child in orchestration.children.values()):
            orchestration.status = "running"
        elif orchestration.status != "cancelled":
            orchestration.status = "completed"
        summary_prefix = "多资产任务完成"
        if orchestration.status == "needs_approval":
            summary_prefix = "多资产任务等待审批"
        elif orchestration.status == "running":
            summary_prefix = "多资产任务运行中"
        elif orchestration.status == "cancelled":
            summary_prefix = "多资产任务已取消"
        elif orchestration.status == "failed":
            summary_prefix = "多资产任务失败"
        elif orchestration.status == "partial_failed":
            summary_prefix = "多资产任务部分失败"
        orchestration.final_summary = (
            f"{summary_prefix}：总数 {len(orchestration.children)}，"
            f"成功 {len(completed)}，失败 {len(failed)}，待审批 {len(needs_approval)}，已取消 {len(cancelled)}。"
        )
        return self._append_event(
            orchestration,
            "orchestration_summary",
            {
                "orchestrationId": orchestration.orchestration_id,
                "status": orchestration.status,
                "finalSummary": orchestration.final_summary,
                "children": [self._child_view(child) for child in orchestration.children.values()],
            },
        )

    def _append_event(
        self,
        orchestration: OrchestrationState,
        kind: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            orchestration.sequence += 1
            orchestration.updated_at = datetime.now(UTC)
            event = {
                "id": f"evt-{uuid.uuid4().hex[:12]}",
                "kind": kind,
                "sequence": orchestration.sequence,
                "ts": orchestration.updated_at.isoformat(),
                **payload,
            }
            orchestration.events.append(event)
            return event

    def _get(self, orchestration_id: str) -> OrchestrationState:
        with self._lock:
            orchestration = self._by_id.get(orchestration_id)
        if orchestration is None:
            raise ValueError("orchestration not found")
        return orchestration

    def _child_for_runtime(self, orchestration: OrchestrationState, runtime_id: str) -> ChildRunState:
        with self._lock:
            for child in orchestration.children.values():
                if child.runtime_id == runtime_id:
                    return child
        raise ValueError("orchestration child runtime not found")

    def _snapshot(self, orchestration: OrchestrationState) -> dict[str, Any]:
        return {
            "orchestrationId": orchestration.orchestration_id,
            "conversationId": orchestration.conversation_id,
            "prompt": orchestration.prompt,
            "targetAssetIds": orchestration.target_asset_ids,
            "targetSelectionSource": orchestration.target_selection_source,
            "targetSelectionReason": orchestration.target_selection_reason,
            "confidence": orchestration.target_selection_confidence,
            "status": orchestration.status,
            "maxConcurrency": orchestration.max_concurrency,
            "children": [self._child_view(child) for child in orchestration.children.values()],
            "finalSummary": orchestration.final_summary,
            "createdAt": orchestration.created_at,
            "updatedAt": orchestration.updated_at,
            "lastSequence": orchestration.sequence,
        }

    def _child_view(self, child: ChildRunState) -> dict[str, Any]:
        return {
            "assetId": child.asset_id,
            "assetName": child.asset_name,
            "runtimeId": child.runtime_id,
            "terminalId": child.terminal_id,
            "status": child.status,
            "summary": child.summary,
            "errorMessage": child.error_message,
            "lastSequence": child.last_sequence,
        }

    def _resolve_model_config(self, session: Session, model_name: str | None):
        default_record = get_default_model_config(session)
        if default_record is None:
            raise ValueError("LLM 模型未配置，请先在设置中添加并设为默认模型。")
        config = self._model_service.from_record(default_record)
        if model_name and model_name != config.model_name:
            config = config.model_copy(update={"model_name": model_name})
        return config
