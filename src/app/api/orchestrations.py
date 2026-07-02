from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.api.console import get_console_app_service
from app.api.conversations import get_conversation_service
from app.api.schemas import (
    ConsoleOrchestrationResolveTargetsRequest,
    ConsoleOrchestrationResolveTargetsResponse,
    ConsoleOrchestrationRunRequest,
    OrchestrationEventsResponse,
    OrchestrationSnapshotView,
)
from app.api.terminal import get_terminal_service
from app.db.session import get_session
from app.services.orchestration_service import OrchestrationService
from app.services.terminal_service import TerminalService


router = APIRouter()
logger = logging.getLogger(__name__)
_orchestration_service = OrchestrationService(console_service=get_console_app_service())


def _sse_event(payload: dict) -> str:
    return f"event: {payload.get('kind', 'message')}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


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
    orchestration_service: OrchestrationService = Depends(get_orchestration_service),
) -> ConsoleOrchestrationResolveTargetsResponse:
    payload = await _parse_request_model(request, ConsoleOrchestrationResolveTargetsRequest)
    try:
        selection = orchestration_service.resolve_targets(
            session=session,
            prompt=payload.prompt,
            current_asset_id=payload.current_asset_id,
            model_name=payload.model_name,
        )
        return ConsoleOrchestrationResolveTargetsResponse(
            targetAssetIds=selection.asset_ids,
            targetSelectionSource=selection.source,
            targetSelectionReason=selection.reason,
            confidence=selection.confidence,
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
    if payload.conversation_id and payload.conversation_id != "console":
        conversation_service = get_conversation_service()
        user_event = {
            "id": f"user-{payload.conversation_id}-{abs(hash(payload.prompt))}",
            "kind": "user",
            "text": payload.prompt,
        }
        try:
            conversation_service.append_events(payload.conversation_id, [user_event])
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Conversation not found") from exc

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
        )
        first_event = next(stream)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    def event_stream():
        yield _sse_event(first_event)
        try:
            for event in stream:
                yield _sse_event(event)
        except Exception as exc:
            logger.exception("orchestration stream failed")
            yield _sse_event(
                {
                    "id": "error-orchestration",
                    "kind": "error",
                    "text": str(exc),
                    "recoverable": True,
                }
            )

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
