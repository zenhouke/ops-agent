import hashlib
import hmac
import json
import threading
from typing import Any, cast

from sqlalchemy import desc
from sqlmodel import Session, select

from app.db.models import AuditLog
from app.services.secret_key import get_ops_agent_secret_key


# Production is intentionally single-process for one data directory.  This lock
# makes the read-previous/write-next chain update atomic across FastAPI worker
# threads; ProcessLock prevents a second Ops Agent process from sharing it.
_audit_chain_lock = threading.RLock()


def _entry_digest(previous_hash: str, payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hmac.new(
        get_ops_agent_secret_key().encode("utf-8"),
        f"{previous_hash}\n{serialized}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _canonical_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize values before both hashing and SQLite type coercion."""
    conversation_id = payload.get("conversation_id")
    return {
        "action": str(payload.get("action") or ""),
        "entity_type": str(payload.get("entity_type") or ""),
        "actor": str(payload.get("actor") or ""),
        "entity_id": _optional_int(payload.get("entity_id")),
        "asset_id": _optional_int(payload.get("asset_id")),
        "conversation_id": None if conversation_id is None else str(conversation_id),
        "task_id": _optional_int(payload.get("task_id")),
        "details": str(payload.get("details") or ""),
    }


def create_audit_log(session: Session, **payload: Any) -> AuditLog:
    with _audit_chain_lock:
        previous = session.exec(
            select(AuditLog).order_by(desc(cast(Any, AuditLog.id))).limit(1)
        ).first()
        previous_hash = previous.entry_hash if previous is not None else ""
        chain_payload = _canonical_payload(payload)
        row = AuditLog(
            **chain_payload,
            previous_hash=previous_hash,
            entry_hash=_entry_digest(previous_hash, chain_payload),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def list_audit_logs(session: Session, limit: int = 100) -> list[AuditLog]:
    return list(
        session.exec(
            select(AuditLog)
            .order_by(desc(cast(Any, AuditLog.created_at)), desc(cast(Any, AuditLog.id)))
            .limit(limit)
        ).all()
    )


def verify_audit_chain(session: Session) -> tuple[bool, int]:
    with _audit_chain_lock:
        rows = list(session.exec(select(AuditLog).order_by(cast(Any, AuditLog.id))).all())
        previous_hash = ""
        for row in rows:
            payload = _canonical_payload({
                "action": row.action,
                "entity_type": row.entity_type,
                "actor": row.actor,
                "entity_id": row.entity_id,
                "asset_id": row.asset_id,
                "conversation_id": row.conversation_id,
                "task_id": row.task_id,
                "details": row.details,
            })
            if row.previous_hash != previous_hash or row.entry_hash != _entry_digest(previous_hash, payload):
                return False, row.id or 0
            previous_hash = row.entry_hash
        return True, len(rows)


def backfill_legacy_audit_chain(session: Session) -> int:
    with _audit_chain_lock:
        rows = list(session.exec(select(AuditLog).order_by(cast(Any, AuditLog.id))).all())
        previous_hash = ""
        updated = 0
        for row in rows:
            payload = _canonical_payload({
                "action": row.action,
                "entity_type": row.entity_type,
                "actor": row.actor,
                "entity_id": row.entity_id,
                "asset_id": row.asset_id,
                "conversation_id": row.conversation_id,
                "task_id": row.task_id,
                "details": row.details,
            })
            expected = _entry_digest(previous_hash, payload)
            if not row.entry_hash:
                row.previous_hash = previous_hash
                row.entry_hash = expected
                session.add(row)
                updated += 1
            elif row.previous_hash != previous_hash or row.entry_hash != expected:
                raise RuntimeError(f"Audit chain verification failed at entry {row.id}")
            previous_hash = row.entry_hash
        if updated:
            session.commit()
        return updated
