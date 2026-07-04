from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.api.console import get_console_app_service
from app.api.conversations import get_conversation_service
from app.api.schemas import (
    ConsoleOrchestrationApprovalRequest,
    ConsoleOrchestrationResolveTargetsRequest,
    ConsoleOrchestrationResolveTargetsResponse,
    ConsoleOrchestrationRunRequest,
    OrchestrationEventsResponse,
    OrchestrationSnapshotView,
    OrchestrationTargetPreparationView,
)
from app.api.terminal import get_terminal_service
from app.db.session import get_session
from app.services.orchestration_service import OrchestrationPermissionDenied, OrchestrationService, OrchestrationStateConflict
from app.services.terminal_service import TerminalService


router = APIRouter()
logger = logging.getLogger(__name__)
_orchestration_service = OrchestrationService(console_service=get_console_app_service())


def _sse_event(payload: dict) -> str:
    return f"event: {payload.get('kind', 'message')}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _persist_conversation_event(conversation_service, conversation_id: str | None, event: dict) -> None:
    if conversation_service is None or not conversation_id or conversation_id == "console":
        return
    try:
        conversation_service.append_events(conversation_id, [event], async_title_generation=False)
    except Exception:
        logger.exception("failed to persist orchestration event conversation_id=%s", conversation_id)


async def _parse_request_model(request: Request, model_type):
    payload = await request.json()
    if isinstance(payload, str):
        payload = json.loads(payload)
    return model_type.model_validate(payload)


def get_orchestration_service() -> OrchestrationService:
    return _orchestration_service


@router.post("/api/console/orchestrations/resolve-targets")
async def resolve_orchestration_targets(
    request: Request,
    session: Session = Depends(get_session),
    terminal_service: TerminalService = Depends(get_terminal_service),
    orchestration_service: OrchestrationService = Depends(get_orchestration_service),
) -> ConsoleOrchestrationResolveTargetsResponse:
    payload = await _parse_request_model(request, ConsoleOrchestrationResolveTargetsRequest)
    try:
        selection, preparations, confirmation_token = orchestration_service.prepare_targets(
            session=session,
            terminal_service=terminal_service,
            prompt=payload.prompt,
            conversation_id=payload.conversation_id,
            current_asset_id=payload.current_asset_id,
            model_name=payload.model_name,
        )
        return ConsoleOrchestrationResolveTargetsResponse(
            targetAssetIds=selection.asset_ids,
            targetSelectionSource=selection.source,
            targetSelectionReason=selection.reason,
            confidence=selection.confidence,
            confirmationToken=confirmation_token,
            preparations=[
                OrchestrationTargetPreparationView(
                    assetId=item.asset_id,
                    assetName=item.asset_name,
                    status=item.status,
                    terminalId=item.terminal_id,
                    reason=item.reason,
                )
                for item in preparations
            ],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/console/orchestrations/run")
async def run_orchestration(
    request: Request,
    session: Session = Depends(get_session),
    terminal_service: TerminalService = Depends(get_terminal_service),
    orchestration_service: OrchestrationService = Depends(get_orchestration_service),
):
    payload = await _parse_request_model(request, ConsoleOrchestrationRunRequest)
    conversation_service = None
    user_event = None
    if payload.conversation_id and payload.conversation_id != "console":
        conversation_service = get_conversation_service()
        try:
            conversation_service.get_conversation(payload.conversation_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Conversation not found") from exc
        user_event = {
            "id": f"user-{payload.conversation_id}-{uuid.uuid4().hex}",
            "kind": "user",
            "text": payload.prompt,
        }

    try:
        stream = orchestration_service.stream_run(
            session=session,
            terminal_service=terminal_service,
            prompt=payload.prompt,
            current_asset_id=payload.current_asset_id,
            target_asset_ids=payload.target_asset_ids,
            conversation_id=payload.conversation_id,
            model_name=payload.model_name,
            selected_skill_name=payload.selected_skill_name,
            max_concurrency=payload.max_concurrency,
            confirmation_token=payload.confirmation_token,
        )
        first_event = next(stream)
        if conversation_service is not None and user_event is not None and payload.conversation_id:
            persisted_events = [user_event]
            if first_event.get("kind") == "orchestration_started":
                persisted_events.append(first_event)
            conversation_service.append_events(payload.conversation_id, persisted_events)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    def event_stream():
        yield _sse_event(first_event)
        try:
            for event in stream:
                _persist_conversation_event(conversation_service, payload.conversation_id, event)
                yield _sse_event(event)
        except Exception as exc:
            logger.exception("orchestration stream failed")
            error_event = {
                "id": "error-orchestration",
                "kind": "error",
                "text": str(exc),
                "recoverable": True,
            }
            _persist_conversation_event(conversation_service, payload.conversation_id, error_event)
            yield _sse_event(error_event)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/api/console/orchestrations/{orchestration_id}/snapshot")
def get_orchestration_snapshot(
    orchestration_id: str,
    orchestration_service: OrchestrationService = Depends(get_orchestration_service),
) -> OrchestrationSnapshotView:
    try:
        return OrchestrationSnapshotView.model_validate(orchestration_service.get_snapshot(orchestration_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/console/orchestrations/{orchestration_id}/events")
def get_orchestration_events(
    orchestration_id: str,
    since: int = 0,
    orchestration_service: OrchestrationService = Depends(get_orchestration_service),
) -> OrchestrationEventsResponse:
    try:
        latest_sequence, events = orchestration_service.events_since(orchestration_id, since)
        return OrchestrationEventsResponse(latestSequence=latest_sequence, events=events)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/console/orchestrations/{orchestration_id}/cancel")
def cancel_orchestration(
    orchestration_id: str,
    orchestration_service: OrchestrationService = Depends(get_orchestration_service),
) -> dict:
    try:
        return orchestration_service.cancel(orchestration_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/console/orchestrations/{orchestration_id}/approval")
async def approve_orchestration_child(
    orchestration_id: str,
    request: Request,
    session: Session = Depends(get_session),
    terminal_service: TerminalService = Depends(get_terminal_service),
    orchestration_service: OrchestrationService = Depends(get_orchestration_service),
):
    payload = await _parse_request_model(request, ConsoleOrchestrationApprovalRequest)
    try:
        orchestration_snapshot = orchestration_service.get_snapshot(orchestration_id)
        conversation_id = str(orchestration_snapshot.get("conversationId") or "")
        conversation_service = get_conversation_service() if conversation_id and conversation_id != "console" else None
        orchestration_service.validate_child_approval_request(
            orchestration_id=orchestration_id,
            runtime_id=payload.runtime_id,
            approval_token=payload.approval_token,
        )
        stream = orchestration_service.stream_child_approval(
            session=session,
            orchestration_id=orchestration_id,
            runtime_id=payload.runtime_id,
            approved=payload.approved,
            approval_token=payload.approval_token,
            allow_prefix=payload.allow_prefix,
            terminal_service=terminal_service,
        )
        first_event = next(stream)
        _persist_conversation_event(conversation_service, conversation_id, first_event)
    except OrchestrationPermissionDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except OrchestrationStateConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    def event_stream():
        yield _sse_event(first_event)
        try:
            for event in stream:
                _persist_conversation_event(conversation_service, conversation_id, event)
                yield _sse_event(event)
        except Exception as exc:
            logger.exception("orchestration approval stream failed")
            error_event = {
                "id": "error-orchestration-approval",
                "kind": "error",
                "text": str(exc),
                "recoverable": True,
            }
            _persist_conversation_event(conversation_service, conversation_id, error_event)
            yield _sse_event(error_event)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
