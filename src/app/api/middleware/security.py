from __future__ import annotations

import asyncio

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_body_bytes: int, max_concurrency: int) -> None:
        if max_body_bytes <= 0 or max_concurrency <= 0:
            raise ValueError("Request limits must be positive integers")
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.semaphore = asyncio.Semaphore(max_concurrency)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        async with self.semaphore:
            request = Request(scope)
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > self.max_body_bytes:
                        response = JSONResponse({"detail": "Request body too large"}, status_code=413)
                        await response(scope, receive, send)
                        return
                except ValueError:
                    response = JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)
                    await response(scope, receive, send)
                    return

            body_parts: list[bytes] = []
            body_size = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                part = message.get("body", b"")
                body_size += len(part)
                if body_size > self.max_body_bytes:
                    response = JSONResponse({"detail": "Request body too large"}, status_code=413)
                    await response(scope, receive, send)
                    return
                body_parts.append(part)
                if not message.get("more_body", False):
                    break
            body = b"".join(body_parts)
            delivered = False

            async def limited_receive() -> Message:
                nonlocal delivered
                if delivered:
                    return {"type": "http.disconnect"}
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}

            await self.app(scope, limited_receive, send)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend([
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'; base-uri 'none'"),
                    (b"cache-control", b"no-store"),
                ])
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
