from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from app.shared.config import MCP_SERVERS_PATH
from app.utils.file_store import atomic_write_json

MCPTransport = Literal["stdio", "http_sse"]
MCPApprovalPolicy = Literal["allow", "ask", "deny"]
MCPConnectionStatus = Literal["untested", "ok", "failed"]
MCPDiscoveryStatus = Literal["never", "ok", "failed"]

_VALID_TRANSPORTS = {"stdio", "http_sse"}
_VALID_APPROVAL_POLICIES = {"allow", "ask", "deny"}
_VALID_CONNECTION_STATUSES = {"untested", "ok", "failed"}
_VALID_DISCOVERY_STATUSES = {"never", "ok", "failed"}
_STORE_LOCK = threading.RLock()
_SECRET_KEY_PATTERN = re.compile(r"(token|password|passwd|secret|api[_-]?key|authorization|cookie|credential)", re.IGNORECASE)
_MASK_RE = re.compile(r"^\*{4}(?:.*)?$")


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _clean_name(value: Any, default: str) -> str:
    text = str(value or "").strip()
    return text or default


def _coerce_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _coerce_str_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def _coerce_schema(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _coerce_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _coerce_transport(value: Any) -> MCPTransport:
    if value in _VALID_TRANSPORTS:
        return cast(MCPTransport, value)
    return "stdio"


def _coerce_approval_policy(value: Any) -> MCPApprovalPolicy:
    if value in _VALID_APPROVAL_POLICIES:
        return cast(MCPApprovalPolicy, value)
    return "ask"


def _coerce_connection_status(value: Any) -> MCPConnectionStatus:
    if value in _VALID_CONNECTION_STATUSES:
        return cast(MCPConnectionStatus, value)
    return "untested"


def _coerce_discovery_status(value: Any) -> MCPDiscoveryStatus:
    if value in _VALID_DISCOVERY_STATUSES:
        return cast(MCPDiscoveryStatus, value)
    return "never"


@dataclass(slots=True)
class MCPToolConfig:
    id: str
    original_name: str
    exposed_name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    approval_policy: MCPApprovalPolicy = "ask"
    enabled: bool = True
    discovered: bool = True
    last_discovered_at: str | None = None
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


@dataclass(slots=True)
class MCPServerConfig:
    id: str
    name: str
    slug: str
    enabled: bool
    transport: MCPTransport
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 30
    connection_status: MCPConnectionStatus = "untested"
    discovery_status: MCPDiscoveryStatus = "never"
    last_error: str = ""
    last_discovered_at: str | None = None
    last_refresh_succeeded: bool = False
    tools: list[MCPToolConfig] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


@dataclass(frozen=True, slots=True)
class DiscoveredMCPTool:
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)


