from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.services.auth_service import is_connection_authorized


PUBLIC_PATHS = {"/health", "/ready", "/api/auth/status"}


class ApiAuthenticationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if (
            request.method == "OPTIONS"
            or request.url.path in PUBLIC_PATHS
            or is_connection_authorized(request)
        ):
            return await call_next(request)
        return JSONResponse(
            status_code=401,
            content={"detail": "Authentication required"},
            headers={"WWW-Authenticate": "Bearer"},
        )
