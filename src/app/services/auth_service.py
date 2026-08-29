from __future__ import annotations

import hmac
import os
import base64

from starlette.requests import HTTPConnection

from app.services.secret_key import get_ops_agent_secret_key


def is_api_authentication_required() -> bool:
    return os.environ.get("OPS_AGENT_AUTH_DISABLED", "false").lower() not in {"1", "true", "yes"}


def get_api_access_token() -> str:
    configured = os.environ.get("OPS_AGENT_API_TOKEN", "").strip()
    return configured or get_ops_agent_secret_key()


def _extract_bearer_token(connection: HTTPConnection) -> str:
    authorization = connection.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer":
        return token.strip()
    return ""


def _extract_websocket_protocol_token(connection: HTTPConnection) -> str:
    protocols = [item.strip() for item in connection.headers.get("sec-websocket-protocol", "").split(",")]
    encoded = next((item.removeprefix("token.") for item in protocols if item.startswith("token.")), "")
    if not encoded:
        return ""
    try:
        padding = "=" * (-len(encoded) % 4)
        return base64.urlsafe_b64decode(f"{encoded}{padding}").decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        return ""


def is_connection_authorized(connection: HTTPConnection, *, websocket_protocol: bool = False) -> bool:
    if not is_api_authentication_required():
        return True
    provided = _extract_bearer_token(connection)
    if not provided and websocket_protocol:
        provided = _extract_websocket_protocol_token(connection)
    expected = get_api_access_token()
    return bool(provided) and hmac.compare_digest(provided, expected)
