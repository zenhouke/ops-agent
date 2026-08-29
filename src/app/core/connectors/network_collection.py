from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Literal

from textfsm import TextFSMError


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
    "cisco_nxos": {
        "facts": (NetworkCollectionCommand("show version"),),
        "interfaces": (NetworkCollectionCommand("show interface"),),
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

_TEXTFSM_PLATFORMS = {
    "cisco": "cisco_ios",
    "cisco_nxos": "cisco_nxos",
    "huawei": "huawei_vrp",
    "h3c": "hp_comware",
    "juniper": "juniper_junos",
}


def collection_commands(vendor: str, kind: NetworkCollectionKind) -> tuple[NetworkCollectionCommand, ...]:
    commands = _COMMANDS.get(vendor, {}).get(kind)
    if not commands:
        raise ValueError(f"Structured {kind} collection is not available for network vendor '{vendor}'.")
    return commands


def parse_collection_output(vendor: str, command: str, raw_output: str) -> list[dict[str, Any]]:
    platform = _TEXTFSM_PLATFORMS.get(vendor)
    if platform is None:
        return []
    from netmiko.utilities import get_structured_data_textfsm

    try:
        parsed = get_structured_data_textfsm(raw_output, platform=platform, command=command)
    except (IndexError, ValueError, TextFSMError):
        parsed = []
    if isinstance(parsed, list) and parsed and all(isinstance(item, dict) for item in parsed):
        return [dict(item) for item in parsed]
    return _fallback_parse(vendor, command, raw_output)


def _fallback_parse(vendor: str, command: str, raw_output: str) -> list[dict[str, Any]]:
    if vendor in {"huawei", "h3c"} and command == "display version":
        fields: dict[str, Any] = {}
        hostname = re.search(r"(?m)^(\S+)\s+\S+\s+uptime is\s+(.+?)\s*$", raw_output)
        if hostname is not None:
            fields["uptime"] = hostname.group(2).strip()
        model = re.search(r"(?m)^(\S+?)(?:\(\S+\))?\s+version information\s*$", raw_output)
        if model is not None:
            fields["model"] = model.group(1)
        version = re.search(r"(?m)^VRP\s+\(R\)\s+software,\s+Version\s+(.+?)\s*$", raw_output)
        if version is not None:
            fields["version"] = version.group(1).strip()
        return [fields] if fields else []
    if vendor in {"huawei", "h3c"} and command == "display interface":
        records: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for line in raw_output.splitlines():
            match = re.match(r"^(\S+)\s+current state\s*:\s*(\S+)", line)
            if match is not None:
                if current is not None:
                    records.append(current)
                current = {"interface": match.group(1), "link_status": match.group(2)}
                continue
            if current is None:
                continue
            protocol = re.match(r"^Line protocol current state\s*:\s*(\S+)", line)
            if protocol is not None:
                current["protocol_status"] = protocol.group(1)
                continue
            description = re.match(r"^Description:\s*(.*?)\s*$", line)
            if description is not None:
                current["description"] = description.group(1)
                continue
            address = re.search(r"Hardware address is\s+(\S+)", line)
            if address is not None:
                current["mac_address"] = address.group(1)
            speed = re.search(r"^Speed:\s*(\d+)", line)
            if speed is not None:
                current["speed"] = speed.group(1)
            mtu = re.search(r"Maximum Frame Length is\s+(\d+)", line)
            if mtu is not None:
                current["mtu"] = mtu.group(1)
        if current is not None:
            records.append(current)
        return records
    if vendor == "huawei" and command == "display lldp neighbor":
        records: list[dict[str, Any]] = []
        local_interface = ""
        current: dict[str, Any] | None = None
        for line in raw_output.splitlines():
            interface = re.match(r"^(\S+)\s+has\s+\d+\s+neighbor", line)
            if interface is not None:
                if current is not None:
                    records.append(current)
                    current = None
                local_interface = interface.group(1)
                continue
            if re.match(r"^Neighbor index\s*:", line):
                if current is not None:
                    records.append(current)
                current = {"local_interface": local_interface}
                continue
            if current is None:
                continue
            field = re.match(r"^([^:]+?)\s*:\s*(.*?)\s*$", line)
            if field is None:
                continue
            key, value = field.group(1).strip(), field.group(2).strip()
            if key == "Port ID":
                current["neighbor_interface"] = value
            elif key == "System name":
                current["neighbor_name"] = value
            elif key == "Management address":
                current["management_address"] = value
            elif key == "Chassis ID":
                current["chassis_id"] = value
        if current is not None:
            records.append(current)
        for item in records:
            if str(item.get("neighbor_name") or "").strip().lower() in {"", "-", "--", "n/a"} and item.get("chassis_id"):
                item["neighbor_name"] = item["chassis_id"]
        return [item for item in records if item.get("neighbor_name")]
    if vendor != "juniper":
        return []
    if command == "show version":
        fields: dict[str, Any] = {}
        for key, target in (("Hostname", "hostname"), ("Model", "model"), ("Junos", "version")):
            match = re.search(rf"(?m)^{key}:\s*(\S.+?)\s*$", raw_output)
            if match is not None:
                fields[target] = match.group(1).strip()
        return [fields] if fields.get("hostname") else []
    if command == "show interfaces":
        records: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for line in raw_output.splitlines():
            match = re.match(
                r"^Physical interface:\s+(\S+),\s+(\S+),\s+Physical link is\s+(\S+)",
                line,
            )
            if match is not None:
                if current is not None:
                    records.append(current)
                current = {
                    "interface": match.group(1),
                    "admin_status": match.group(2),
                    "link_status": match.group(3),
                }
                continue
            if current is None:
                continue
            description = re.match(r"^\s+Description:\s*(.+?)\s*$", line)
            if description is not None:
                current["description"] = description.group(1)
                continue
            link = re.search(r"Link-level type:\s*([^,]+),\s*MTU:\s*(\d+)", line)
            if link is not None:
                current["hardware_type"] = link.group(1).strip()
                current["mtu"] = link.group(2)
            address = re.search(r"Current address:\s*([^,\s]+)", line)
            if address is not None:
                current["mac_address"] = address.group(1)
        if current is not None:
            records.append(current)
        return records
    if command == "show lldp neighbors":
        records = []
        for line in raw_output.splitlines():
            columns = re.split(r"\s{2,}", line.strip())
            if len(columns) < 5 or columns[0].lower().startswith(("local interface", "local port")):
                continue
            local_interface, _parent, _chassis, remote_port = columns[:4]
            neighbor_name = " ".join(columns[4:]).strip()
            if not local_interface or not neighbor_name:
                continue
            records.append({
                "local_interface": local_interface,
                "neighbor_interface": remote_port,
                "neighbor_name": neighbor_name,
            })
        return records
    return []


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
            "softwareVersion": _pick(normalized, "version", "software_version", "os_version", "junos_version", "nxos", "os"),
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
