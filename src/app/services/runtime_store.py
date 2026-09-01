from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_
from sqlmodel import Session, col, select

from app.db.models import AgentRuntimeEventRecord, AgentRuntimeRecord
from app.db.session import engine
from app.services.instance_service import get_instance_info


TERMINAL_RUN_STATES = {"terminal", "interrupted"}


def interruption_recovery(status: str) -> tuple[str, str]:
    if status == "approving":
        return "restart_and_reapprove", "command_approval"
    if status == "waiting_terminal_approval":
        return "restart_and_request_terminal", "terminal_approval"
    if status == "waiting_user_input":
        return "restart_with_operator_reply", "operator_input"
    return "restart_from_conversation", "agent_execution"


def _now() -> datetime:
    return datetime.now(UTC)


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def _encode(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=_json_default)


def _decode(payload: str) -> dict[str, Any]:
    value = json.loads(payload or "{}")
    return value if isinstance(value, dict) else {}


class RuntimeStore:
    def __init__(self) -> None:
        self._instance_id = get_instance_info().instance_id
        self._lease_seconds = self._read_lease_seconds()

    def save_snapshot(self, snapshot: dict[str, Any], *, run_state: str) -> None:
        runtime_id = str(snapshot["runtime_id"])
        with Session(engine) as session:
            record = session.get(AgentRuntimeRecord, runtime_id)
            if record is None:
                record = AgentRuntimeRecord(
                    runtime_id=runtime_id,
                    conversation_id=str(snapshot["conversation_id"]),
                    asset_id=int(snapshot["asset_id"]),
                    terminal_id=snapshot.get("terminal_id"),
                    status=str(snapshot["status"]),
                    mode="agent",
                    run_state=run_state,
                    owner_instance_id=self._instance_id,
                    lease_expires_at=self._lease_expiry(run_state),
                    sequence=int(snapshot.get("last_sequence") or 0),
                    snapshot_json=_encode(snapshot),
                    created_at=self._as_datetime(snapshot.get("created_at")),
                    updated_at=self._as_datetime(snapshot.get("updated_at")),
                )
            else:
                self._apply_snapshot(record, snapshot, run_state=run_state)
            session.add(record)
            session.commit()

    def append_event(
        self,
        snapshot: dict[str, Any],
        event: dict[str, Any],
        *,
        run_state: str,
    ) -> None:
        runtime_id = str(snapshot["runtime_id"])
        sequence = int(event.get("sequence") or 0)
        with Session(engine) as session:
            record = session.get(AgentRuntimeRecord, runtime_id)
            if record is None:
                record = AgentRuntimeRecord(
                    runtime_id=runtime_id,
                    conversation_id=str(snapshot["conversation_id"]),
                    asset_id=int(snapshot["asset_id"]),
                    terminal_id=snapshot.get("terminal_id"),
                    status=str(snapshot["status"]),
                    owner_instance_id=self._instance_id,
                    lease_expires_at=self._lease_expiry(run_state),
                )
            self._apply_snapshot(record, snapshot, run_state=run_state)
            session.add(record)
            existing = session.exec(
                select(AgentRuntimeEventRecord).where(
                    AgentRuntimeEventRecord.runtime_id == runtime_id,
                    AgentRuntimeEventRecord.sequence == sequence,
                )
            ).first()
            if existing is None:
                session.add(AgentRuntimeEventRecord(
                    runtime_id=runtime_id,
                    conversation_id=record.conversation_id,
                    sequence=sequence,
                    kind=str(event.get("kind") or "message"),
                    payload_json=_encode(event),
                    created_at=self._as_datetime(event.get("occurredAt") or event.get("ts")),
                ))
            session.commit()

    def get_snapshot(self, runtime_id: str) -> dict[str, Any] | None:
        with Session(engine) as session:
            record = session.get(AgentRuntimeRecord, runtime_id)
            return _decode(record.snapshot_json) if record is not None else None

    def list_snapshots(self, conversation_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        with Session(engine) as session:
            records = session.exec(
                select(AgentRuntimeRecord)
                .where(AgentRuntimeRecord.conversation_id == conversation_id)
                .order_by(AgentRuntimeRecord.updated_at.desc())  # type: ignore[attr-defined]
                .limit(limit)
            ).all()
            return [_decode(record.snapshot_json) for record in records]

    def events_since(self, runtime_id: str, since: int) -> tuple[int, list[dict[str, Any]]]:
        with Session(engine) as session:
            record = session.get(AgentRuntimeRecord, runtime_id)
            if record is None:
                raise ValueError("runtime not found")
            rows = session.exec(
                select(AgentRuntimeEventRecord)
                .where(
                    AgentRuntimeEventRecord.runtime_id == runtime_id,
                    AgentRuntimeEventRecord.sequence > since,
                )
                .order_by(AgentRuntimeEventRecord.sequence)  # type: ignore[arg-type]
            ).all()
            return record.sequence, [_decode(row.payload_json) for row in rows]

    def recover_interrupted(self) -> int:
        recovered = 0
        with Session(engine) as session:
            records = session.exec(
                select(AgentRuntimeRecord).where(
                    AgentRuntimeRecord.run_state.not_in(TERMINAL_RUN_STATES),  # type: ignore[attr-defined]
                    or_(
                        col(AgentRuntimeRecord.owner_instance_id) == self._instance_id,
                        col(AgentRuntimeRecord.owner_instance_id) == "",
                        col(AgentRuntimeRecord.lease_expires_at).is_(None),
                        col(AgentRuntimeRecord.lease_expires_at) <= _now(),
                    ),
                )
            ).all()
            for record in records:
                snapshot = _decode(record.snapshot_json)
                recovery_action, recovery_checkpoint = interruption_recovery(
                    str(snapshot.get("status") or record.status)
                )
                sequence = max(record.sequence, int(snapshot.get("last_sequence") or 0)) + 1
                occurred_at = _now()
                message = "Runtime was interrupted by an application restart."
                for request in snapshot.get("terminal_requests") or []:
                    if request.get("userDecisionStatus") == "pending":
                        request["userDecisionStatus"] = "expired"
                        request["approvalToken"] = None
                        request["failureReason"] = message
                for authorization in snapshot.get("terminal_authorizations") or []:
                    if authorization.get("status") == "active":
                        authorization["status"] = "expired"
                        authorization["revokeReason"] = message
                snapshot.update({
                    "status": "failed",
                    "run_state": "interrupted",
                    "error_message": message,
                    "last_sequence": sequence,
                    "updated_at": occurred_at.isoformat(),
                    "cancel_requested": False,
                    "recovery_action": recovery_action,
                    "recovery_checkpoint": recovery_checkpoint,
                })
                event_id = str(uuid.uuid4())
                event = {
                    "id": event_id,
                    "eventId": event_id,
                    "kind": "error",
                    "runtimeId": record.runtime_id,
                    "sequence": sequence,
                    "ts": occurred_at.isoformat(),
                    "occurredAt": occurred_at.isoformat(),
                    "text": message,
                    "recoverable": True,
                    "interrupted": True,
                    "recoveryAction": recovery_action,
                    "recoveryCheckpoint": recovery_checkpoint,
                }
                record.status = "failed"
                record.run_state = "interrupted"
                record.lease_expires_at = None
                record.sequence = sequence
                record.snapshot_json = _encode(snapshot)
                record.updated_at = occurred_at
                session.add(record)
                session.add(AgentRuntimeEventRecord(
                    runtime_id=record.runtime_id,
                    conversation_id=record.conversation_id,
                    sequence=sequence,
                    kind="error",
                    payload_json=_encode(event),
                    created_at=occurred_at,
                ))
                recovered += 1
            session.commit()
        return recovered

    def prune(self, *, retention_days: int = 30) -> int:
        cutoff = _now() - timedelta(days=retention_days)
        with Session(engine) as session:
            records = session.exec(
                select(AgentRuntimeRecord).where(AgentRuntimeRecord.updated_at < cutoff)
            ).all()
            runtime_ids = [record.runtime_id for record in records]
            if not runtime_ids:
                return 0
            events = session.exec(
                select(AgentRuntimeEventRecord).where(
                    AgentRuntimeEventRecord.runtime_id.in_(runtime_ids)  # type: ignore[attr-defined]
                )
            ).all()
            for event in events:
                session.delete(event)
            for record in records:
                session.delete(record)
            session.commit()
            return len(records)

    def _apply_snapshot(
        self,
        record: AgentRuntimeRecord,
        snapshot: dict[str, Any],
        *,
        run_state: str,
    ) -> None:
        record.status = str(snapshot["status"])
        record.mode = "agent"
        record.run_state = run_state
        record.owner_instance_id = self._instance_id
        record.lease_expires_at = self._lease_expiry(run_state)
        record.sequence = int(snapshot.get("last_sequence") or 0)
        record.terminal_id = snapshot.get("terminal_id")
        record.snapshot_json = _encode(snapshot)
        record.updated_at = self._as_datetime(snapshot.get("updated_at"))

    def _lease_expiry(self, run_state: str) -> datetime | None:
        if run_state in TERMINAL_RUN_STATES:
            return None
        return _now() + timedelta(seconds=self._lease_seconds)

    def _read_lease_seconds(self) -> int:
        try:
            configured = int(os.getenv("OPS_AGENT_RUNTIME_LEASE_SECONDS", "300"))
        except ValueError:
            configured = 300
        return max(15, min(configured, 3600))

    def _as_datetime(self, value: object) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        return _now()
