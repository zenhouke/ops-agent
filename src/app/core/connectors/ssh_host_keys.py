from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def configured_known_hosts_path() -> Path | None:
    value = os.environ.get("OPS_AGENT_KNOWN_HOSTS_FILE", "").strip()
    return Path(value).expanduser() if value else None


def configure_strict_ssh_client(client: Any) -> Any:
    """Load operator-approved host keys and reject every unknown or changed key."""
    import paramiko

    client.load_system_host_keys()
    known_hosts = configured_known_hosts_path()
    if known_hosts is not None:
        if not known_hosts.is_file():
            raise ValueError(f"Configured SSH known-hosts file does not exist: {known_hosts}")
        client.load_host_keys(str(known_hosts))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    return client


def strict_netmiko_options() -> dict[str, object]:
    options: dict[str, object] = {
        "ssh_strict": True,
        "system_host_keys": True,
    }
    known_hosts = configured_known_hosts_path()
    if known_hosts is not None:
        if not known_hosts.is_file():
            raise ValueError(f"Configured SSH known-hosts file does not exist: {known_hosts}")
        options.update({"alt_host_keys": True, "alt_key_file": str(known_hosts)})
    return options
