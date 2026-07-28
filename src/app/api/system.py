from fastapi import APIRouter
import serial.tools.list_ports

from app.api.schemas import SerialPortView
from app.services.observability_service import get_observability_service
from app.services.instance_service import get_instance_info
from app.services.ops_plugin_service import get_ops_plugin_service

router = APIRouter()


@router.get("/api/system/runtime-health")
def get_runtime_health() -> dict:
    snapshot = get_observability_service().runtime_snapshot()
    snapshot["instance"] = get_instance_info().as_payload()
    snapshot["opsPlugins"] = get_ops_plugin_service().summary()
    return snapshot


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
