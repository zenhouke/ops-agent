from __future__ import annotations

import queue
import threading
import uuid
from collections import deque
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
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


@dataclass
class ChildRunState:
    asset_id: int
    asset_name: str
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
        self._lock = threading.Lock()

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
    ) -> Iterator[dict[str, Any]]:
        selection = self.resolve_targets(
            session=session,
            prompt=prompt,
            current_asset_id=current_asset_id,
            model_name=model_name,
            explicit_asset_ids=target_asset_ids,
        )

        children: dict[int, ChildRunState] = {}
        for asset_id in selection.asset_ids:
            asset = get_asset(session, asset_id)
            if asset is None or asset.id is None:
                raise ValueError(f"Asset not found: {asset_id}")
            children[asset.id] = ChildRunState(asset_id=asset.id, asset_name=asset.name)

        orchestration = OrchestrationState(
            orchestration_id=f"orch-{uuid.uuid4().hex}",
            conversation_id=conversation_id,
            prompt=prompt,
            target_asset_ids=list(children.keys()),
            target_selection_source=selection.source,
            target_selection_reason=selection.reason,
            target_selection_confidence=selection.confidence,
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
            },
        )

        event_queue: queue.Queue[dict[str, Any] | None] = queue.Queue()
        remaining = len(orchestration.children)

        with ThreadPoolExecutor(max_workers=orchestration.max_concurrency) as executor:
            for child in orchestration.children.values():
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
                item = event_queue.get()
                if item is None:
                    remaining -= 1
                    continue
                yield item

        yield self._finalize(orchestration)
        yield self._append_event(
            orchestration,
            "orchestration_completed"
            if orchestration.status in {"completed", "partial_failed", "needs_approval"}
            else "orchestration_failed",
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
            if child.status == "pending":
                child.status = "cancelled"
        return self._append_event(
            orchestration,
            "orchestration_cancelled",
            {"orchestrationId": orchestration_id, "status": "cancelled"},
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
                    "status": child.status,
                },
            )
        )

        try:
            from app.db.session import Session as DbSession
            from app.db.session import engine

            with DbSession(engine) as child_session:
                stream = self._console_service.stream_run(
                    session=child_session,
                    prompt=child_prompt,
                    asset_id=child.asset_id,
                    terminal_id=None,
                    model_name=model_name,
                    selected_skill_name=selected_skill_name,
                    conversation_id=orchestration.conversation_id,
                    mode="agent",
                    terminal_service=terminal_service,
                )
                for event in stream:
                    runtime_id = str(event.get("runtimeId") or "")
                    if runtime_id and child.runtime_id is None:
                        child.runtime_id = runtime_id
                    child.last_sequence = int(event.get("sequence") or child.last_sequence or 0)
                    kind = str(event.get("kind") or "")
                    if kind == "message_update" and event.get("type") == "ask":
                        child.status = "needs_approval"
                        orchestration.status = "needs_approval"
                    if kind in {"completed", "final"}:
                        child.status = "completed"
                        child.summary = str(event.get("summary") or event.get("text") or "")
                    if kind in {"failed", "error"}:
                        child.status = "failed"
                        child.error_message = str(
                            event.get("error") or event.get("text") or "Child runtime failed."
                        )
                    event_queue.put(
                        self._append_event(
                            orchestration,
                            "child_runtime_event",
                            {
                                "orchestrationId": orchestration.orchestration_id,
                                "runtimeId": child.runtime_id,
                                "assetId": child.asset_id,
                                "assetName": child.asset_name,
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
                        "errorMessage": child.error_message,
                    },
                )
            )
        finally:
            terminal_kind = "child_runtime_completed" if child.status == "completed" else "child_runtime_status"
            event_queue.put(
                self._append_event(
                    orchestration,
                    terminal_kind,
                    {
                        "orchestrationId": orchestration.orchestration_id,
                        "runtimeId": child.runtime_id,
                        "assetId": child.asset_id,
                        "assetName": child.asset_name,
                        "status": child.status,
                        "summary": child.summary,
                        "errorMessage": child.error_message,
                    },
                )
            )
            event_queue.put(None)

    def _child_prompt(self, *, prompt: str, asset_id: int, asset_name: str) -> str:
        return (
            "你是多资产任务中的一个子任务执行者。\n"
            f"总任务：{prompt}\n"
            f"当前目标资产：{asset_name} (asset_id={asset_id})\n\n"
            "只在当前资产上执行必要检查。不要请求其他资产的终端访问。\n"
            "完成后给出结构化摘要：执行了什么、关键输出、是否成功、异常或建议。"
        )

    def _finalize(self, orchestration: OrchestrationState) -> dict[str, Any]:
        completed = [child for child in orchestration.children.values() if child.status == "completed"]
        failed = [child for child in orchestration.children.values() if child.status == "failed"]
        needs_approval = [child for child in orchestration.children.values() if child.status == "needs_approval"]
        if needs_approval:
            orchestration.status = "needs_approval"
        elif completed and failed:
            orchestration.status = "partial_failed"
        elif failed and not completed:
            orchestration.status = "failed"
        elif orchestration.status != "cancelled":
            orchestration.status = "completed"
        orchestration.final_summary = (
            f"多资产任务完成：总数 {len(orchestration.children)}，"
            f"成功 {len(completed)}，失败 {len(failed)}，待审批 {len(needs_approval)}。"
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
