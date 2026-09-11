from __future__ import annotations

import hmac
import os
import base64

from collections.abc import Mapping

from app.shared.secret_key import get_ops_agent_secret_key


def is_api_authentication_required() -> bool:
    return os.environ.get("OPS_AGENT_AUTH_DISABLED", "false").lower() not in {"1", "true", "yes"}


def get_api_access_token() -> str:
    configured = os.environ.get("OPS_AGENT_API_TOKEN", "").strip()
    return configured or get_ops_agent_secret_key()


def _extract_bearer_token(headers: Mapping[str, str]) -> str:
    authorization = headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer":
        return token.strip()
    return ""


def _extract_websocket_protocol_token(headers: Mapping[str, str]) -> str:
    protocols = [item.strip() for item in headers.get("sec-websocket-protocol", "").split(",")]
    encoded = next((item.removeprefix("token.") for item in protocols if item.startswith("token.")), "")
    if not encoded:
        return ""
    try:
        padding = "=" * (-len(encoded) % 4)
        return base64.urlsafe_b64decode(f"{encoded}{padding}").decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        return ""


def is_request_authorized(headers: Mapping[str, str], *, websocket_protocol: bool = False) -> bool:
    if not is_api_authentication_required():
        return True
    provided = _extract_bearer_token(headers)
    if not provided and websocket_protocol:
        provided = _extract_websocket_protocol_token(headers)
    expected = get_api_access_token()
    return bool(provided) and hmac.compare_digest(provided, expected)
