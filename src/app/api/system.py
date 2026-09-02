from fastapi import APIRouter, Depends, Query
import serial.tools.list_ports
from sqlmodel import Session

from app.api.schemas import SerialPortView
from app.services.observability_service import get_observability_service
from app.services.instance_service import get_instance_info
from app.services.ops_plugin_service import get_ops_plugin_service
from app.build_metadata import BUILD_SHA, VERSION
from app.db.migrations import CURRENT_SCHEMA_VERSION
from app.db.repositories.audit import list_audit_logs, verify_audit_chain
from app.db.session import get_session
from app.services.redaction_service import RedactionService
from app.shared.config import APP_DIR

router = APIRouter()


@router.get("/api/system/runtime-health")
def get_runtime_health() -> dict:
    snapshot = get_observability_service().runtime_snapshot()
    snapshot["instance"] = get_instance_info().as_payload()
    snapshot["opsPlugins"] = get_ops_plugin_service().summary()
    snapshot["version"] = VERSION
    snapshot["buildSha"] = BUILD_SHA
    snapshot["schemaVersion"] = CURRENT_SCHEMA_VERSION
    return snapshot


@router.get("/api/system/audit-logs")
def export_audit_logs(
    limit: int = Query(default=500, ge=1, le=5000),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    valid, checked = verify_audit_chain(session)
    rows = list_audit_logs(session, limit=limit)
    return {
        "chainValid": valid,
        "checkedEntries": checked,
        "entries": [
            {
                "id": row.id,
                "action": row.action,
                "entityType": row.entity_type,
                "actor": row.actor,
                "entityId": row.entity_id,
                "assetId": row.asset_id,
                "conversationId": row.conversation_id,
                "taskId": row.task_id,
                "details": row.details,
                "previousHash": row.previous_hash,
                "entryHash": row.entry_hash,
                "createdAt": row.created_at.isoformat(),
            }
            for row in rows
        ],
    }


@router.get("/api/system/diagnostics")
def get_diagnostics(session: Session = Depends(get_session)) -> dict[str, object]:
    chain_valid, checked = verify_audit_chain(session)
    log_path = APP_DIR / "logs" / "ops-agent.log"
    log_tail = ""
    if log_path.is_file():
        with log_path.open("r", encoding="utf-8", errors="replace") as handle:
            log_tail = "".join(handle.readlines()[-200:])
    return {
        "version": VERSION,
        "buildSha": BUILD_SHA,
        "schemaVersion": CURRENT_SCHEMA_VERSION,
        "runtime": get_observability_service().runtime_snapshot(),
        "instance": get_instance_info().as_payload(),
        "audit": {"chainValid": chain_valid, "checkedEntries": checked},
        "logTail": RedactionService().redact_text(log_tail),
    }


@router.get("/api/system/serial-ports", response_model=list[SerialPortView])
def list_serial_ports() -> list[SerialPortView]:
    """
    Get a list of available serial ports in the system.
    """
    ports = serial.tools.list_ports.comports()
    result = []
    for port in ports:
        result.append(
            SerialPortView(
                device=port.device,
                description=port.description,
                hwid=port.hwid,
                name=port.name,
                vid=port.vid,
                pid=port.pid,
                serial_number=port.serial_number,
                location=port.location,
                manufacturer=port.manufacturer,
                product=port.product,
                interface=port.interface,
            )
        )
    return result
