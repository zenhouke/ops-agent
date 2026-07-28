from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.runtime.control import get_runtime_control
from app.services.observability_service import trace_operation


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        started = time.monotonic()
        control = get_runtime_control()
        control.metrics.increment("http_requests")
        attributes = {
            "http.request.method": request.method,
            "url.path": request.url.path,
            "ops.request_id": request_id,
        }
        with trace_operation("http.request", attributes):
            try:
                response = await call_next(request)
            except Exception:
                control.metrics.increment("http_errors")
                raise
        response.headers["x-request-id"] = request_id
        response.headers["server-timing"] = f"app;dur={(time.monotonic() - started) * 1000:.2f}"
        if response.status_code >= 500:
            control.metrics.increment("http_errors")
        return response
