from __future__ import annotations

import re
import time
from typing import Any

from app.core.connectors.device_profiles import GENERIC_DEVICE_PROFILE, select_device_profile
from app.core.connectors.network_cli import analyze_transcript, strip_pager_markers
from app.core.connectors.network_collection import (
    NetworkCollectionKind,
    collection_commands,
    normalize_collection_record,
    parse_collection_output,
)
from app.services.jumpserver_ssh_client import JumpServerSSHClient


_ANSI_CSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_PAGER_DISABLE_COMMANDS = {
    "cisco": "terminal length 0",
    "cisco_nxos": "terminal length 0",
    "huawei": "screen-length 0 temporary",
    "h3c": "screen-length 0 temporary",
    "juniper": "set cli screen-length 0",
}


class JumpServerMenuConnector:
    def __init__(
        self,
        gateway: JumpServerSSHClient,
        *,
        asset_name: str,
        address: str,
        account: str,
        asset_type: str,
        shell_kind: str,
    ) -> None:
        self.gateway = gateway
        self.asset_name = asset_name
        self.address = address
        self.account = account
        self.asset_type = asset_type
        self.shell_kind = shell_kind
        self.client: Any | None = None
        self.channel: Any | None = None
        self._initial_output = ""
        self._network_session_prepared = False

    def open_interactive(self) -> object:
        if self.channel is None:
            self.client, self.channel, self._initial_output = self.gateway.open_asset_channel(
                asset_name=self.asset_name,
                address=self.address,
                account=self.account,
            )
        return self.channel

    def read(self) -> str:
        if self._initial_output:
            output = self._initial_output
            self._initial_output = ""
            return output
        if self.channel is None or not self.channel.recv_ready():
            return ""
        return self.channel.recv(65535).decode("utf-8", errors="ignore")

    def write(self, data: str) -> None:
        if self.channel is not None:
            self.channel.send(data.encode("utf-8", errors="ignore"))

    def resize(self, cols: int, rows: int) -> None:
        if self.channel is not None:
            self.channel.resize_pty(width=cols, height=rows)

    def run_command(self, command: str) -> str:
        profile = select_device_profile(self.asset_type, self.shell_kind)
        return self._execute_command(command, timeout=30.0, profile=profile)

    def collection_plan(self, kind: NetworkCollectionKind) -> dict[str, Any]:
        profile = select_device_profile(self.asset_type, self.shell_kind)
        if profile is None or profile.vendor == "generic":
            raise ValueError("Select an explicit supported network vendor before topology collection.")
        vendor = profile.vendor
        if vendor == "cisco" and re.search(r"(?:nexus|n\d+k|9\d{4})", self.asset_name, flags=re.IGNORECASE):
            vendor = "cisco_nxos"
        commands = collection_commands(vendor, kind)
        return {
            "vendor": vendor,
            "deviceType": self.asset_type,
            "commands": [{"command": item.command, "protocol": item.protocol} for item in commands],
        }

    def collect_structured(self, kind: NetworkCollectionKind, *, read_timeout: float = 30.0) -> dict[str, Any]:
        plan = self.collection_plan(kind)
        vendor = str(plan["vendor"])
        profile = select_device_profile(self.asset_type, self.shell_kind) or GENERIC_DEVICE_PROFILE
        self._prepare_network_session(vendor, profile, read_timeout)
        records: list[dict[str, Any]] = []
        sources: list[dict[str, Any]] = []
        for spec in collection_commands(vendor, kind):
            raw = self._execute_command(spec.command, timeout=read_timeout, profile=profile)
            parsed_records = parse_collection_output(vendor, spec.command, raw)
            if parsed_records:
                normalized = [
                    normalize_collection_record(kind, item, protocol=spec.protocol)
                    for item in parsed_records
                ]
                records.extend(normalized)
                sources.append({
                    "command": spec.command,
                    "protocol": spec.protocol,
                    "parsed": True,
                    "recordCount": len(normalized),
                })
                continue
            analysis = analyze_transcript(raw, profile)
            sources.append({
                "command": spec.command,
                "protocol": spec.protocol,
                "parsed": False,
                "error": analysis.matched_error,
                "rawExcerpt": raw[:12000],
                "truncated": len(raw) > 12000,
            })
        return {
            "kind": kind,
            "vendor": "cisco" if vendor == "cisco_nxos" else vendor,
            "deviceType": self.asset_type,
            "records": records,
            "sources": sources,
        }

    def _prepare_network_session(self, vendor: str, profile: Any, timeout: float) -> None:
        if self._network_session_prepared:
            return
        if self.channel is None:
            self.open_interactive()
        if self.channel is not None:
            self.channel.resize_pty(width=512, height=1000)
        command = _PAGER_DISABLE_COMMANDS.get(vendor)
        if command:
            self._execute_command(command, timeout=min(timeout, 10.0), profile=profile)
        self._network_session_prepared = True

    def _execute_command(self, command: str, *, timeout: float, profile: Any | None) -> str:
        if self.channel is None:
            self.open_interactive()
        assert self.channel is not None
        self._initial_output = ""
        self.channel.send((command.rstrip("\n") + "\n").encode())
        chunks: list[str] = []
        deadline = time.monotonic() + timeout
        quiet_since: float | None = None
        handled_pager_count = 0
        saw_command_echo = False
        while time.monotonic() < deadline:
            if self.channel.recv_ready():
                chunks.append(self.channel.recv(65535).decode("utf-8", errors="ignore"))
                quiet_since = time.monotonic()
                cleaned = self._clean_output("".join(chunks))
                saw_command_echo = saw_command_echo or command.strip().casefold() in cleaned.casefold()
                if profile is not None:
                    pager_count = sum(
                        len(re.findall(pattern, cleaned, flags=re.IGNORECASE))
                        for pattern in profile.pager_patterns
                    )
                    if pager_count > handled_pager_count:
                        self.channel.send(b" ")
                        handled_pager_count = pager_count
                if profile is not None and saw_command_echo and any(
                    re.search(pattern, cleaned)
                    for pattern in profile.prompt_patterns
                ):
                    break
            elif profile is None and quiet_since is not None and time.monotonic() - quiet_since >= 1.0:
                break
            else:
                time.sleep(0.05)
        output = self._clean_output("".join(chunks))
        if profile is not None:
            output = strip_pager_markers(output, profile)
        return self._strip_command_echo(output, command)

    @staticmethod
    def _clean_output(value: str) -> str:
        cleaned = _ANSI_CSI.sub("", value).replace("\r", "")
        while "\b" in cleaned:
            collapsed = re.sub(r"[^\n]\x08", "", cleaned)
            if collapsed == cleaned:
                break
            cleaned = collapsed
        return cleaned.replace("\b", "")

    @staticmethod
    def _strip_command_echo(value: str, command: str) -> str:
        command_pattern = re.escape(command.strip())
        lines = value.splitlines()
        filtered: list[str] = []
        removed = False
        for line in lines:
            stripped = line.strip()
            is_echo = stripped == command.strip() or bool(
                re.match(rf"^.*[>#\]]\s*{command_pattern}\s*$", stripped)
            )
            if not removed and is_echo:
                removed = True
                continue
            filtered.append(line)
        while filtered and not filtered[-1].strip():
            filtered.pop()
        if filtered and re.match(r"^.*(?:>|#|\])\s*$", filtered[-1].strip()):
            filtered.pop()
        return "\n".join(filtered)

    def close(self) -> None:
        if self.channel is not None:
            self.channel.close()
            self.channel = None
        if self.client is not None:
            self.client.close()
            self.client = None
