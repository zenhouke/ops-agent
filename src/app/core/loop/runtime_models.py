from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from app.core.loop.loop_state import LoopState


TerminalRequestDecisionStatus = Literal["pending", "approved", "rejected", "expired"]
TerminalCreationStatus = Literal["not_started", "opening", "opened", "failed"]
TerminalAuthorizationStatus = Literal["active", "revoked", "closed", "expired", "replaced"]
TerminalAuthorizationSource = Literal["initial_asset", "user_approved_request"]
TerminalAuthorizationApprover = Literal["system", "user"]


@dataclass
class PendingTerminalRequest:
    request_id: str
    runtime_id: str
    conversation_id: str
    asset_id: int
    asset_name: str
    reason: str
    token_hash: str
    user_decision_status: TerminalRequestDecisionStatus
    terminal_creation_status: TerminalCreationStatus
    created_at: datetime
    expires_at: datetime
    decided_at: datetime | None = None
    terminal_started_at: datetime | None = None
    terminal_finished_at: datetime | None = None
    failure_reason: str | None = None
    approval_token: str | None = None


@dataclass
class RuntimeTerminalAuthorization:
    authorization_id: str
    runtime_id: str
    conversation_id: str
    asset_id: int
    asset_name: str
    terminal_id: str
    source: TerminalAuthorizationSource
    approved_by: TerminalAuthorizationApprover
    request_id: str | None
    status: TerminalAuthorizationStatus
    output_cursor: int
    created_at: datetime
    updated_at: datetime
    asset_type: str = ""
    asset_summary: str = ""
    shell_type: str = "unknown"
    os_type: str = "unknown"
    execution_profile: str = "posix-shell"
    device_vendor: str | None = None
    device_context: str = ""
    revoked_at: datetime | None = None
    revoke_reason: str | None = None
    replaced_by_authorization_id: str | None = None


@dataclass
class RuntimeState:
    runtime_id: str
    conversation_id: str
    asset_id: int
    terminal_id: str | None
    state: LoopState
    events: deque[dict]
    sequence: int
    created_at: datetime
    updated_at: datetime
    terminal_requests: dict[str, PendingTerminalRequest] = field(default_factory=dict)
    terminal_authorizations: dict[str, RuntimeTerminalAuthorization] = field(default_factory=dict)
    execution_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
