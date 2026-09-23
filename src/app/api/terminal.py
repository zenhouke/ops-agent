from fastapi import APIRouter, Depends, HTTPException, Response, WebSocket
from pydantic import BaseModel
from sqlmodel import Session

from app.api.assets import to_asset_view
from app.api.schemas import AssetContextView, TerminalEventSummaryView
from app.composition import get_terminal_service
from app.db.session import get_session
from app.services.asset_service import get_asset_record
from app.api.terminal_channel import WebSocketTerminalChannel
from app.services.auth_service import is_request_authorized
from app.utils.local_terminal_asset import build_local_terminal_asset
from app.services.terminal_service import TerminalService
from app.services.ssh_host_key_service import confirm_host_key

router = APIRouter()

_terminal_service = get_terminal_service()


class TerminalSessionRequest(BaseModel):
    asset_id: int


class TerminalSessionResponse(BaseModel):
    terminal_id: str | None
    channel: str | None
    error: str
    host_key: dict[str, str] | None = None


class HostKeyConfirmationRequest(BaseModel):
    asset_id: int | None = None
    token: str


@router.post("/api/terminal/host-key/confirm", status_code=204)
def confirm_terminal_host_key(payload: HostKeyConfirmationRequest) -> Response:
    try:
        confirm_host_key(payload.asset_id, payload.token)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=503, detail="无法保存主机信任记录，请检查 known_hosts 文件的写入权限。") from exc
    return Response(status_code=204)


class TerminalContextRequest(BaseModel):
    selection_label: str
    selected_text: str


class TerminalContextResponse(BaseModel):
    terminal_id: str
    selection_label: str
    selected_text: str


def _get_terminal_asset(session: Session, asset_id: int):
    asset = get_asset_record(session, asset_id)
    if asset is None and asset_id == 0:
        return build_local_terminal_asset()
    return asset


def _runtime_manager():
    from app.composition import get_console_app_service

    return get_console_app_service().runtime_manager


@router.post("/api/terminal/sessions")
def open_terminal_session(
    payload: TerminalSessionRequest,
    session: Session = Depends(get_session),
    terminal_service: TerminalService = Depends(get_terminal_service),
) -> TerminalSessionResponse:
    asset = _get_terminal_asset(session, payload.asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    result = terminal_service.open_session(asset)
    return TerminalSessionResponse(
        terminal_id=result.get("terminal_id"),
        channel=result.get("channel"),
        error=result.get("error", ""),
        host_key=result.get("host_key"),
    )


@router.get("/api/assets/{asset_id}/context")
def get_asset_context(
    asset_id: int,
    session: Session = Depends(get_session),
    terminal_service: TerminalService = Depends(get_terminal_service),
) -> AssetContextView:
    asset = get_asset_record(session, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")

    return AssetContextView(
        asset=to_asset_view(asset),
        recent_terminal_events=[
            TerminalEventSummaryView.model_validate(event)
            for event in terminal_service.list_recent_events_for_asset(asset_id)
        ],
    )


@router.post("/api/terminal/sessions/{terminal_id}/context")
def attach_terminal_context(
    terminal_id: str,
    payload: TerminalContextRequest,
    terminal_service: TerminalService = Depends(get_terminal_service),
) -> TerminalContextResponse:
    attachment = terminal_service.attach_context(
        terminal_id,
        payload.selection_label,
        payload.selected_text,
    )
    return TerminalContextResponse(
        terminal_id=attachment.terminal_id,
        selection_label=attachment.selection_label,
        selected_text=attachment.selected_text,
    )


@router.websocket("/api/terminal/sessions/{terminal_id}/ws")
async def stream_terminal_session(
    websocket: WebSocket,
    terminal_id: str,
    terminal_service: TerminalService = Depends(get_terminal_service),
) -> None:
    if not is_request_authorized(websocket.headers, websocket_protocol=True):
        await websocket.close(code=4401, reason="Authentication required")
        return
    await terminal_service.stream_session(terminal_id, WebSocketTerminalChannel(websocket), subprotocol="ops-agent")


@router.delete("/api/terminal/sessions/{terminal_id}", status_code=204)
def close_terminal_session(
    terminal_id: str,
    terminal_service: TerminalService = Depends(get_terminal_service),
) -> Response:
    closed = terminal_service.close_session(terminal_id)
    if not closed:
        raise HTTPException(status_code=404, detail="Terminal session not found")
    _runtime_manager().revoke_authorizations_for_terminal(
        terminal_id,
        status="closed",
        reason="terminal_closed",
    )
    return Response(status_code=204)


class TerminalReconnectRequest(BaseModel):
    asset_id: int


@router.post("/api/terminal/sessions/{terminal_id}/reconnect")
def reconnect_terminal_session(
    terminal_id: str,
    payload: TerminalReconnectRequest,
    session: Session = Depends(get_session),
    terminal_service: TerminalService = Depends(get_terminal_service),
) -> TerminalSessionResponse:
    asset = _get_terminal_asset(session, payload.asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    result = terminal_service.open_session(asset)
    if not result.get("terminal_id"):
        return TerminalSessionResponse(
            terminal_id=result.get("terminal_id"),
            channel=result.get("channel"),
            error=result.get("error", ""),
            host_key=result.get("host_key"),
        )
    closed = terminal_service.close_session(terminal_id)
    if not closed:
        terminal_service.close_session(str(result.get("terminal_id")))
        raise HTTPException(status_code=404, detail="Terminal session not found")
    _runtime_manager().revoke_authorizations_for_terminal(
        terminal_id,
        status="replaced",
        reason="terminal_reconnected",
    )
    return TerminalSessionResponse(
        terminal_id=result.get("terminal_id"),
        channel=result.get("channel"),
        error=result.get("error", ""),
    )
