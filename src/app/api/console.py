import json
import logging
import time
from collections.abc import Iterable, Iterator
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.api.assets import to_asset_view
from app.api.conversations import get_conversation_service
from app.api.groups import to_asset_group_view
from app.api.ssh_keys import to_ssh_key_view
from app.api.schemas import ConsoleApprovalRequest, ConsoleBootstrapView, ConsoleRunRequest, RuntimeEventsResponse, RuntimeSnapshotView, RuntimeSummaryView, TerminalRequestDecisionRequest
from app.services.ssh_key_service import list_ssh_key_records
from app.api.terminal import get_terminal_service
from app.db.repositories.models import get_default_model_config, list_model_configs
from app.db.session import get_session
from app.services.asset_service import get_asset_record, list_asset_group_records, list_asset_records

from app.utils.local_terminal_asset import build_local_terminal_asset
from app.services.model_service import ModelService
from app.services.terminal_service import TerminalService
from app.services.console_app_service import ConsoleAppService, TaskOrchestrator
from app.shared.enums import AssetType

router = APIRouter()
_console_app_service = ConsoleAppService()
logger = logging.getLogger(__name__)

INCIDENT_MODE_INSTRUCTION = """[Incident response mode]
Treat the following request as an operational incident. Establish impact, scope, timeline, and evidence before proposing changes. Separate verified facts from hypotheses. Prefer read-only diagnostics first. For every mutating command, state risk, expected result, and rollback, and preserve the normal human approval workflow. Finish with a concise incident summary and reusable runbook steps.

Operator request:
"""


def _sse_event(payload: dict) -> str:
    event_id = payload.get("eventId") or (
        f"{payload.get('runtimeId')}:{payload.get('sequence')}"
        if payload.get("runtimeId") and payload.get("sequence") is not None
        else payload.get("id")
    )
    id_line = f"id: {str(event_id).replace(chr(10), '').replace(chr(13), '')}\n" if event_id else ""
    return f"{id_line}event: {payload.get('kind', 'message')}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _conversation_event(payload: dict) -> dict | None:
    kind = payload.get("kind")
    if kind in {"context_status", "delta"}:
        return None
    if kind == "message_update":
        return {**payload, "kind": "message"}
    return dict(payload)


def _persisted_stream(conversation_id: str | None, events: Iterable[dict]) -> Iterator[str]:
    service = get_conversation_service() if conversation_id and conversation_id != "console" else None
    pending_messages: dict[str, dict] = {}
    last_message_write: dict[str, float] = {}

    def persist(event: dict) -> bool:
        if service is None or conversation_id is None:
            return True
        try:
            service.append_events(conversation_id, [event])
            return True
        except Exception:
            logger.exception("Failed to persist stream event conversation_id=%s", conversation_id)
            return False

    try:
        for event in events:
            outgoing = dict(event)
            persisted_event = _conversation_event(event)
            if service is not None and persisted_event is not None:
                message_id = str(persisted_event.get("id") or "") if persisted_event.get("kind") == "message" else ""
                is_partial_message = bool(message_id and persisted_event.get("partial", False))
                now = time.monotonic()
                if is_partial_message and now - last_message_write.get(message_id, 0.0) < 0.5:
                    pending_messages[message_id] = persisted_event
                    outgoing["persistenceStatus"] = "saving"
                else:
                    if message_id:
                        pending_messages.pop(message_id, None)
                        last_message_write[message_id] = now
                    outgoing["persistenceStatus"] = "saved" if persist(persisted_event) else "failed"
            yield _sse_event(outgoing)
    finally:
        for pending_event in pending_messages.values():
            persist(pending_event)


def _streaming_response(events: Iterable[str]) -> StreamingResponse:
    return StreamingResponse(
        events,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


async def _parse_request_model(request: Request, model_type):
    payload = await request.json()
    if isinstance(payload, str):
        payload = json.loads(payload)
    return model_type.model_validate(payload)


def get_task_orchestrator(terminal_service: TerminalService = Depends(get_terminal_service)) -> TaskOrchestrator:
    return _console_app_service.build_orchestrator(terminal_service)


def get_console_app_service() -> ConsoleAppService:
    return _console_app_service


@router.get("/api/console/bootstrap")
def get_console_bootstrap(
    session: Session = Depends(get_session),
    terminal_service: TerminalService = Depends(get_terminal_service),
) -> ConsoleBootstrapView:
    assets = list_asset_records(session)
    model_service = ModelService()
    default_record = get_default_model_config(session)
    default_config = model_service.from_record(default_record) if default_record is not None else model_service.load_settings()
    model_options = [record.model_name for record in list_model_configs(session)] or model_service.list_available_models(default_config.provider, session)
    if default_config.model_name and default_config.model_name not in model_options:
        model_options = [default_config.model_name, *model_options]
    local_terminal_asset = next((asset for asset in assets if asset.asset_type == AssetType.LOCAL_TERMINAL.value), None)
    if local_terminal_asset is None:
        local_terminal_asset = build_local_terminal_asset()
    terminal_session_result = terminal_service.open_session(local_terminal_asset, reuse_existing=True)
    terminal_session_id = terminal_session_result.get("terminal_id")
    terminal_output = ""
    if terminal_session_id:
        terminal_output = terminal_service.read_buffered_output(terminal_session_id)

    return ConsoleBootstrapView(
        assets=[to_asset_view(asset) for asset in assets],
        groups=[to_asset_group_view(group) for group in list_asset_group_records(session)],
        historyByAsset={},
        modelOptions=model_options,
        terminalSessionId=terminal_session_id,
        terminalSessionChannel=terminal_session_result.get("channel"),
        terminalSessionError=terminal_session_result.get("error", ""),
        initialPrompt="",
        terminalOutput=terminal_output,
        initialEvents=[],
        sshKeys=[to_ssh_key_view(record) for record in list_ssh_key_records(session)],
    )


@router.post("/api/console/run")
async def run_console_agent(
    request: Request,
    session: Session = Depends(get_session),
    orchestrator: TaskOrchestrator = Depends(get_task_orchestrator),
):
    import time as _time
    t_start = _time.monotonic()
    payload = await _parse_request_model(request, ConsoleRunRequest)
    effective_prompt = (
        f"{INCIDENT_MODE_INSTRUCTION}{payload.prompt}"
        if payload.mode == "incident"
        else payload.prompt
    )
    t_parse = _time.monotonic()
    if payload.conversation_id and payload.conversation_id != "console":
        conversation_service = get_conversation_service()
        user_event = {
            "id": f"user-{uuid4().hex}",
            "kind": "user",
            "text": payload.prompt,
            "mode": payload.mode,
        }
        try:
            conversation_service.append_events(payload.conversation_id, [user_event])
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Conversation not found") from exc
    t_persist = _time.monotonic()
    asset_id = payload.asset_id
    if asset_id is None:
        local_terminal_asset = next((asset for asset in list_asset_records(session) if asset.asset_type == AssetType.LOCAL_TERMINAL.value), None)
        asset_id = local_terminal_asset.id if local_terminal_asset is not None and local_terminal_asset.id is not None else 0
    if asset_id is None:
        raise HTTPException(status_code=400, detail="Asset id is required")
    
    try:
        stream = orchestrator.stream_run(
            session=session,
            prompt=effective_prompt,
            asset_id=asset_id,
            terminal_id=payload.terminal_id,
            model_name=payload.model_name,
            selected_skill_name=payload.selected_skill_name,
            conversation_id=payload.conversation_id,
        )
        first_event = next(stream)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    def event_stream():
        yield first_event
        t_first_event = None
        try:
            for event in stream:
                if t_first_event is None:
                    t_first_event = _time.monotonic()
                yield event
        except Exception as exc:
            logger.exception("console.run stream failed conversation_id=%s", payload.conversation_id)
            yield {"id": f"error-run-{uuid4().hex}", "kind": "error", "text": str(exc), "recoverable": True}

    persisted_conversation_id = payload.conversation_id if payload.conversation_id != "console" else None
    return _streaming_response(_persisted_stream(persisted_conversation_id, event_stream()))


@router.get("/api/console/conversations/{conversation_id}/runtimes")
def list_conversation_runtimes(conversation_id: str) -> list[RuntimeSummaryView]:
    snapshots = _console_app_service.runtime_manager.list_runtime_snapshots(conversation_id)
    return [RuntimeSummaryView.model_validate(snapshot) for snapshot in snapshots]


@router.get("/api/console/runtimes/{runtime_id}/snapshot")
def get_runtime_snapshot(runtime_id: str) -> RuntimeSnapshotView:
    snapshot = _console_app_service.runtime_manager.get_snapshot(runtime_id)
    return RuntimeSnapshotView.model_validate(snapshot, from_attributes=True)


@router.get("/api/console/runtimes/{runtime_id}/events")
def get_runtime_events(runtime_id: str, since: int = 0) -> RuntimeEventsResponse:
    latest_sequence, events = _console_app_service.runtime_manager.events_since(runtime_id, since)
    return RuntimeEventsResponse(latest_sequence=latest_sequence, events=[dict(event) for event in events])


@router.post("/api/console/runtimes/{runtime_id}/reconnect")
def reconnect_runtime_stream(
    runtime_id: str,
    since: int = 0,
    terminal_service: TerminalService = Depends(get_terminal_service),
):
    runtime = _console_app_service.runtime_manager.get_runtime(runtime_id)
    if runtime is None:
        raise HTTPException(status_code=404, detail="Runtime not found.")
    stream = _console_app_service.stream_reconnect(
        runtime_id=runtime_id,
        since=since,
        terminal_service=terminal_service,
    )
    return _streaming_response(_persisted_stream(runtime.conversation_id, stream))


@router.post("/api/console/runtimes/{runtime_id}/cancel")
def cancel_runtime(runtime_id: str) -> dict:
    try:
        return _console_app_service.cancel_runtime(runtime_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/console/terminal-requests/{request_id}/decision")
async def decide_terminal_request(
    request_id: str,
    request: Request,
    session: Session = Depends(get_session),
    terminal_service: TerminalService = Depends(get_terminal_service),
    orchestrator: TaskOrchestrator = Depends(get_task_orchestrator),
):
    payload = await _parse_request_model(request, TerminalRequestDecisionRequest)
    try:
        runtime = _console_app_service.runtime_manager.get_runtime(payload.runtime_id)
        if runtime is None:
            raise ValueError("runtime not found")
        terminal_request = runtime.terminal_requests.get(request_id)
        if terminal_request is None:
            raise KeyError("terminal request not found")
        asset = get_asset_record(session, terminal_request.asset_id)
        if asset is None:
            raise LookupError("asset not found")
        result = await _console_app_service.runtime_manager.decide_terminal_request(
            payload.runtime_id,
            request_id,
            approval_token=payload.approval_token,
            approved=payload.approved,
            terminal_service=terminal_service,
            asset=asset,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result["status"] == "expired":
        raise HTTPException(status_code=409, detail=result)
    if result.get("terminalCreationStatus") == "failed":
        raise HTTPException(status_code=502, detail=result)

    response_event = {
        "id": f"evt-terminal-decision-{request_id}",
        "kind": "terminal_session_opened" if result.get("status") == "approved" else "terminal_session_rejected",
        "runtimeId": payload.runtime_id,
        "requestId": result.get("requestId"),
        "authorizationId": result.get("authorizationId"),
        "assetId": result.get("assetId"),
        "assetName": result.get("assetName"),
        "terminalId": result.get("terminalId"),
        "terminalCreationStatus": result.get("terminalCreationStatus"),
        "status": result.get("status"),
        "channel": result.get("channel"),
        "reason": result.get("failureReason") or result.get("status"),
    }
    stream = orchestrator.stream_after_terminal_request(
        runtime_id=payload.runtime_id,
        resume_message=str(result.get("resumeMessage") or "Terminal request was rejected by the user."),
        authorization_id=result.get("authorizationId"),
    )

    def event_stream():
        yield response_event
        try:
            for event in stream:
                yield event
        except Exception as exc:
            yield {"id": f"error-terminal-decision-{uuid4().hex}", "kind": "error", "text": str(exc), "recoverable": True}

    return _streaming_response(_persisted_stream(runtime.conversation_id, event_stream()))


@router.post("/api/console/approval")
async def approve_console_agent(
    request: Request,
    session: Session = Depends(get_session),
    orchestrator: TaskOrchestrator = Depends(get_task_orchestrator),
):
    payload = await _parse_request_model(request, ConsoleApprovalRequest)
    runtime = _console_app_service.runtime_manager.get_runtime(payload.runtime_id)
    conversation_id = runtime.conversation_id if runtime is not None else None
    stream = orchestrator.stream_approve(
        session=session,
        runtime_id=payload.runtime_id,
        approved=payload.approved,
        approval_token=payload.approval_token,
        allow_prefix=payload.allow_prefix,
    )

    def event_stream():
        try:
            for event in stream:
                yield event
        except Exception as exc:
            yield {"id": f"error-approve-{uuid4().hex}", "kind": "error", "text": str(exc), "recoverable": True}

    return _streaming_response(_persisted_stream(conversation_id, event_stream()))
