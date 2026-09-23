from __future__ import annotations

import base64
import hashlib
import os
import threading
from pathlib import Path
from typing import Any

import paramiko

from app.shared.config import APP_DIR

_write_lock = threading.Lock()


class UnknownSSHHostKey(paramiko.SSHException):
    def __init__(self, hostname: str, key: paramiko.PKey):
        self.hostname = hostname
        self.key = key
        self.fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip("=")
        super().__init__(f"首次连接 {hostname}，请确认 SSH 主机指纹 {self.fingerprint}")


class ConfirmHostKeyPolicy(paramiko.RejectPolicy):
    def missing_host_key(self, client, hostname, key):
        raise UnknownSSHHostKey(hostname, key)


def configured_known_hosts_path() -> Path | None:
    value = os.environ.get("OPS_AGENT_KNOWN_HOSTS_FILE", "").strip()
    return Path(value).expanduser() if value else APP_DIR / "ssh_known_hosts"


def configure_strict_ssh_client(client: Any) -> Any:
    """Load operator-approved host keys and reject every unknown or changed key."""
    client.load_system_host_keys()
    known_hosts = configured_known_hosts_path()
    if known_hosts is not None:
        if not known_hosts.is_file() and os.environ.get("OPS_AGENT_KNOWN_HOSTS_FILE", "").strip():
            raise ValueError(f"Configured SSH known-hosts file does not exist: {known_hosts}")
        if known_hosts.is_file():
            client.load_host_keys(str(known_hosts))
    client.set_missing_host_key_policy(ConfirmHostKeyPolicy())
    return client


def trust_host_key(hostname: str, key: paramiko.PKey) -> None:
    """Append an explicitly confirmed key; never replace existing host identity."""
    if not hostname or any(char.isspace() for char in hostname):
        raise ValueError("Invalid SSH hostname")
    with _write_lock:
        client = configure_strict_ssh_client(paramiko.SSHClient())
        try:
            system_keys = paramiko.HostKeys()
            system_path = Path.home() / ".ssh" / "known_hosts"
            if system_path.is_file():
                system_keys.load(str(system_path))
            for keys in (system_keys, client.get_host_keys()):
                existing = keys.lookup(hostname)
                if existing and not keys.check(hostname, key):
                    raise ValueError("SSH 主机密钥已变化，拒绝覆盖已有信任记录。请核实服务器身份。")
            if client.get_host_keys().check(hostname, key):
                return
            path = configured_known_hosts_path()
            assert path is not None
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            # Preserve comments, hashed names and all unrelated entries.
            with path.open("a+", encoding="utf-8") as stream:
                stream.seek(0)
                contents = stream.read()
                if contents and not contents.endswith("\n"):
                    stream.write("\n")
                stream.write(f"{hostname} {key.get_name()} {key.get_base64()}\n")
            if os.name != "nt":
                path.chmod(0o600)
        finally:
            client.close()


def strict_netmiko_options() -> dict[str, object]:
    options: dict[str, object] = {
        "ssh_strict": True,
        "system_host_keys": True,
    }
    known_hosts = configured_known_hosts_path()
    if known_hosts is not None:
        if not known_hosts.is_file() and os.environ.get("OPS_AGENT_KNOWN_HOSTS_FILE", "").strip():
            raise ValueError(f"Configured SSH known-hosts file does not exist: {known_hosts}")
        options.update({"alt_host_keys": True, "alt_key_file": str(known_hosts)})
    return options
