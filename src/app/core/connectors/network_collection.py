from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


NetworkCollectionKind = Literal["facts", "interfaces", "neighbors"]


@dataclass(frozen=True, slots=True)
class NetworkCollectionCommand:
    command: str
    protocol: str | None = None


_COMMANDS: dict[str, dict[NetworkCollectionKind, tuple[NetworkCollectionCommand, ...]]] = {
    "cisco": {
        "facts": (NetworkCollectionCommand("show version"),),
        "interfaces": (NetworkCollectionCommand("show interfaces"),),
        "neighbors": (
            NetworkCollectionCommand("show lldp neighbors detail", "lldp"),
            NetworkCollectionCommand("show cdp neighbors detail", "cdp"),
        ),
    },
    "huawei": {
        "facts": (NetworkCollectionCommand("display version"),),
        "interfaces": (NetworkCollectionCommand("display interface"),),
        "neighbors": (NetworkCollectionCommand("display lldp neighbor", "lldp"),),
    },
    "h3c": {
        "facts": (NetworkCollectionCommand("display version"),),
        "interfaces": (NetworkCollectionCommand("display interface"),),
        "neighbors": (NetworkCollectionCommand("display lldp neighbor-information verbose", "lldp"),),
    },
    "juniper": {
        "facts": (NetworkCollectionCommand("show version"),),
        "interfaces": (NetworkCollectionCommand("show interfaces"),),
        "neighbors": (NetworkCollectionCommand("show lldp neighbors", "lldp"),),
    },
}


def collection_commands(vendor: str, kind: NetworkCollectionKind) -> tuple[NetworkCollectionCommand, ...]:
    commands = _COMMANDS.get(vendor, {}).get(kind)
    if not commands:
        raise ValueError(f"Structured {kind} collection is not available for network vendor '{vendor}'.")
    return commands


def normalize_collection_record(
    kind: NetworkCollectionKind,
    record: dict[str, Any],
    *,
    protocol: str | None = None,
) -> dict[str, Any]:
    normalized = {_normalize_key(key): value for key, value in record.items()}
    if kind == "facts":
        return _compact({
            "hostname": _pick(normalized, "hostname", "host_name"),
            "model": _pick(normalized, "hardware", "model", "platform", "chassis"),
            "serialNumber": _pick(normalized, "serial", "serial_number", "chassis_sn"),
            "softwareVersion": _pick(normalized, "version", "software_version", "os_version", "junos_version"),
            "image": _pick(normalized, "running_image", "software_image"),
            "uptime": _pick(normalized, "uptime"),
            "rawFields": normalized,
        })
    if kind == "interfaces":
        return _compact({
            "name": _pick(normalized, "interface", "interface_name", "port", "name"),
            "description": _pick(normalized, "description", "desc"),
            "status": _pick(normalized, "link_status", "status", "physical_status", "admin_status"),
            "protocolStatus": _pick(normalized, "protocol_status", "line_protocol", "protocol"),
            "macAddress": _pick(normalized, "mac_address", "hardware_address", "address"),
            "ipAddress": _pick(normalized, "ip_address", "ip_address_primary", "ipv4_address"),
            "prefixLength": _pick(normalized, "prefix_length", "prefix"),
            "mtu": _pick(normalized, "mtu"),
            "speed": _pick(normalized, "speed", "bandwidth"),
            "rawFields": normalized,
        })
    return _compact({
        "protocol": protocol,
        "localInterface": _pick(normalized, "local_interface", "local_port", "local_intf", "local_interface_name"),
        "neighborName": _pick(normalized, "neighbor", "neighbor_name", "destination_host", "system_name", "device_id"),
        "neighborInterface": _pick(normalized, "neighbor_interface", "remote_port", "port_id", "remote_interface", "port_id_outgoing_port"),
        "managementAddress": _pick(normalized, "management_ip", "management_address", "mgmt_address", "entry_address"),
        "platform": _pick(normalized, "platform", "system_description"),
        "capabilities": _pick(normalized, "capabilities", "capability"),
        "rawFields": normalized,
    })


def _normalize_key(key: Any) -> str:
    return str(key).strip().lower().replace("-", "_").replace(" ", "_")


def _pick(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, "", []):
            return value
    return None


def _compact(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if value not in (None, "", [])}
