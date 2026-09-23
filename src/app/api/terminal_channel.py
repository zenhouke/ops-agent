from typing import Any

from starlette.websockets import WebSocket, WebSocketDisconnect

from app.services.terminal_channel import TerminalChannelClosed


class WebSocketTerminalChannel:
    def __init__(self, websocket: WebSocket) -> None:
        self._websocket = websocket

    async def accept(self, *, subprotocol: str | None = None) -> None:
        await self._websocket.accept(subprotocol=subprotocol)

    async def close(self, *, code: int) -> None:
        await self._websocket.close(code=code)

    async def receive_json(self) -> dict[str, Any]:
        try:
            return await self._websocket.receive_json()
        except WebSocketDisconnect as exc:
            raise TerminalChannelClosed() from exc

    async def send_json(self, data: dict[str, Any]) -> None:
        try:
            await self._websocket.send_json(data)
        except WebSocketDisconnect as exc:
            raise TerminalChannelClosed() from exc
