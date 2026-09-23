from __future__ import annotations

import hashlib
import math
import re
import time
from io import StringIO
from typing import Any
from urllib.parse import urlparse

import paramiko

from app.core.connectors.ssh_host_keys import configure_strict_ssh_client
from app.services.jumpserver_client import JumpServerError
from app.services.operation_progress import OperationProgress


_ANSI_CSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_ANSI_OSC = re.compile(r"\x1b\].*?(?:\x07|\x1b\\)")
_ASSET_ROW = re.compile(
    r"^\s*(?P<row_id>\d+)\s*\|\s*(?P<name>.*?)\s*\|\s*(?P<address>.*?)\s*\|\s*(?P<platform>.*?)\s*\|",
)
_PAGE = re.compile(r"(?:页码|Page)\s*[:：]\s*(\d+).*?(?:总页数|Total\s*pages?)\s*[:：]\s*(\d+).*?(?:总数量|Total(?:\s*count)?)\s*[:：]\s*(\d+)", re.IGNORECASE)


class JumpServerSSHClient:
    def __init__(self, *, gateway_url: str, username: str, private_key: str, timeout: float = 20.0, asset_connect_timeout: float = 90.0) -> None:
        endpoint = urlparse(gateway_url)
        if endpoint.scheme != "ssh" or not endpoint.hostname:
            raise JumpServerError("JumpServer SSH gateway URL must use ssh://host:port.")
        self.host = endpoint.hostname
        self.port = endpoint.port or 2222
        self.username = username
        self.private_key_text = private_key
        if not math.isfinite(asset_connect_timeout) or asset_connect_timeout <= 0:
            raise JumpServerError("JumpServer asset connection timeout must be a positive finite number.")
        self.asset_connect_timeout = asset_connect_timeout
        self.timeout = timeout
        self.org_name = ""

    def profile(self) -> dict[str, Any]:
        client = self._connect()
        try:
            return {"username": self.username}
        finally:
            client.close()

    def list_all_assets(self, progress: OperationProgress | None = None) -> list[dict[str, Any]]:
        client = self._connect()
        channel = None
        try:
            channel = client.invoke_shell(term="xterm-256color", width=500, height=48)
            self._read_until(channel, ("Opt>",))
            channel.send(b"p\n")
            assets: list[dict[str, Any]] = []
            previous_page = 0
            while True:
                if progress:
                    progress.checkpoint()
                page_text = self._read_until(channel, ("[Host]>",))
                cleaned = self._clean(page_text)
                assets.extend(self._parse_assets(cleaned))
                page_match = _PAGE.search(cleaned)
                if page_match is None:
                    raise JumpServerError("无法识别 JumpServer 资产分页，已取消同步以避免导入不完整资产。")
                current_page, total_pages, total_count = map(int, page_match.groups())
                if total_count == 0 and not assets:
                    return []
                if current_page <= previous_page:
                    raise JumpServerError("JumpServer 资产分页未前进，已取消同步。")
                previous_page = current_page
                if progress:
                    progress.report(message=f"读取 SSH 资产第 {current_page}/{total_pages} 页", total=total_count, completed=len(assets))
                if current_page >= total_pages:
                    if len(assets) != total_count:
                        raise JumpServerError("JumpServer 资产数量与分页总数不一致，已取消同步。")
                    break
                channel.send(b"n\n")
            return self._deduplicate(assets)
        finally:
            if channel is not None:
                try:
                    channel.send(b"q\n")
                    channel.close()
                except Exception:
                    pass
            client.close()

    def discover_default_account(self, *, asset_name: str, address: str) -> str:
        client = self._connect()
        channel = None
        try:
            channel = client.invoke_shell(term="xterm-256color", width=500, height=48)
            self._read_until(channel, ("Opt>",))
            channel.send(f"/{asset_name}\n".encode())
            search_output = self._clean(self._read_until(channel, ("[Host]>",)))
            row_id = self._find_asset_row(search_output, asset_name=asset_name, address=address, org_name=self.org_name)
            if row_id is None:
                raise JumpServerError("JumpServer could not uniquely locate this imported asset.")
            channel.send(f"{row_id}\n".encode())
            connection_output = self._clean(
                self._read_until(channel, ("开始连接到", "Connecting to", "[Account]>", "[User]>", "Opt>"), timeout=self.asset_connect_timeout),
            )
            if "[Account]>" in connection_output or "[User]>" in connection_output:
                raise JumpServerError(
                    "This asset has multiple permitted accounts; select a target account in JumpServer asset settings.",
                )
            match = re.search(r"(?:开始连接到|Connecting to)\s+([^@\n]+)@", connection_output)
            if match is None:
                raise JumpServerError("JumpServer did not reveal the selected target account.")
            label = match.group(1).strip()
            username_match = re.search(r"\(([^()]+)\)$", label)
            return (username_match.group(1) if username_match else label).strip()
        finally:
            if channel is not None:
                channel.close()
            client.close()

    def open_asset_channel(
        self,
        *,
        asset_name: str,
        address: str,
        account: str,
    ) -> tuple[paramiko.SSHClient, paramiko.Channel, str]:
        client = self._connect()
        channel = None
        try:
            channel = client.invoke_shell(term="xterm-256color", width=500, height=48)
            self._read_until(channel, ("Opt>",))
            channel.send(f"/{asset_name}\n".encode())
            search_raw = self._read_until(channel, ("[Host]>",))
            search_output = self._clean(search_raw)
            row_id = self._find_asset_row(search_output, asset_name=asset_name, address=address, org_name=self.org_name)
            if row_id is None:
                raise JumpServerError("JumpServer could not uniquely locate this imported asset.")
            channel.send(f"{row_id}\n".encode())
            connection_raw = self._read_until(
                channel,
                ("开始连接到", "Connecting to", "[Account]>", "[User]>", "Opt>"),
                timeout=self.asset_connect_timeout,
            )
            connection_output = self._clean(connection_raw)
            if "[Account]>" in connection_output or "[User]>" in connection_output:
                if not account:
                    raise JumpServerError(
                        "This asset has multiple permitted accounts; select a target account in JumpServer asset settings.",
                    )
                channel.send(f"/{account}\n".encode())
                account_raw = self._read_until(channel, ("[Account]>", "[User]>"))
                account_row = self._find_text_row(self._clean(account_raw), account)
                if account_row is None:
                    raise JumpServerError("The selected JumpServer target account is not available for this asset.")
                channel.send(f"{account_row}\n".encode())
                connection_raw += self._read_until(channel, ("开始连接到", "Connecting to", "Opt>"), timeout=self.asset_connect_timeout)
            connection_raw += self._read_until_quiet(channel)
            settled_output = self._clean(connection_raw).casefold()
            failure_markers = (
                "[host]>",
                "网络不通",
                "连接超时",
                "connection timed out",
                "no route to host",
                "connect failed",
            )
            if any(marker in settled_output for marker in failure_markers):
                raise JumpServerError("JumpServer could not reach the selected asset.")
            # Do not leak the KoKo navigation menu into the target terminal.  Only
            # keep the connection banner and target greeting.
            return client, channel, self._connection_banner(connection_raw)
        except Exception:
            if channel is not None:
                channel.close()
            client.close()
            raise

    def _connect(self) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        configure_strict_ssh_client(client)
        try:
            client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                pkey=self.load_private_key(self.private_key_text),
                allow_agent=False,
                look_for_keys=False,
                timeout=self.timeout,
                auth_timeout=self.timeout,
                banner_timeout=self.timeout,
            )
        except Exception:
            client.close()
            raise
        transport = client.get_transport()
        if transport is not None:
            transport.set_keepalive(30)
        return client

    def _read_until(self, channel: paramiko.Channel, markers: tuple[str, ...], *, timeout: float | None = None) -> str:
        wait_seconds = self.timeout if timeout is None else timeout
        deadline = time.monotonic() + wait_seconds
        chunks: list[str] = []
        while time.monotonic() < deadline:
            if channel.recv_ready():
                chunks.append(channel.recv(65535).decode("utf-8", errors="ignore"))
                combined = "".join(chunks)
                cleaned = self._clean(combined)
                if any(marker in cleaned for marker in markers):
                    return combined
            elif channel.closed:
                break
            else:
                time.sleep(0.05)
        if channel.closed:
            raise JumpServerError("JumpServer SSH 连接已关闭，未收到预期菜单或连接提示。")
        stage = "连接目标设备" if timeout is not None else "等待菜单"
        raise JumpServerError(f"JumpServer {stage}超时（{wait_seconds:g} 秒），未收到预期提示。请检查目标连通性或菜单交互。")

    def _read_until_quiet(self, channel: paramiko.Channel, quiet_seconds: float = 0.6) -> str:
        deadline = time.monotonic() + self.timeout
        chunks: list[str] = []
        last_received_at: float | None = None
        while time.monotonic() < deadline:
            if channel.recv_ready():
                chunks.append(channel.recv(65535).decode("utf-8", errors="ignore"))
                last_received_at = time.monotonic()
            elif last_received_at is not None and time.monotonic() - last_received_at >= quiet_seconds:
                break
            elif channel.closed:
                break
            else:
                time.sleep(0.05)
        return "".join(chunks)

    @staticmethod
    def load_private_key(private_key: str):
        last_error: Exception | None = None
        for key_type in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey):
            try:
                return key_type.from_private_key(StringIO(private_key.strip()))
            except Exception as exc:
                last_error = exc
        raise JumpServerError("JumpServer SSH private key is invalid or requires an unsupported passphrase.") from last_error

    @staticmethod
    def _clean(value: str) -> str:
        without_osc = _ANSI_OSC.sub("", value)
        without_csi = _ANSI_CSI.sub("", without_osc)
        while "\b" in without_csi:
            collapsed = re.sub(r"[^\n]\x08", "", without_csi)
            if collapsed == without_csi:
                break
            without_csi = collapsed
        return without_csi.replace("\b", "").replace("\r", "")

    def _parse_assets(self, value: str) -> list[dict[str, Any]]:
        assets: list[dict[str, Any]] = []
        for line in value.splitlines():
            match = _ASSET_ROW.match(line)
            if match is None:
                continue
            name = match.group("name").strip()
            address = match.group("address").strip()
            platform = match.group("platform").strip()
            columns = line.split("|")
            org_name = columns[4].strip() if len(columns) >= 6 else ""
            if not name or not address:
                continue
            unsupported = any(word in platform.lower() for word in ("mariadb", "mysql", "postgres", "oracle", "sqlserver", "windows", "kubernetes"))
            identity = f"{org_name}\0{name}\0{address}" if org_name else f"{name}\0{address}"
            external_id = "ssh-" + hashlib.sha256(identity.encode()).hexdigest()
            assets.append({
                "id": external_id,
                "name": name,
                "org_name": org_name,
                "address": address,
                "platform": platform,
                "category": "",
                "type": "",
                "protocols": [] if unsupported else [{"name": "ssh", "port": 22}],
                "permed_accounts": [],
            })
        return assets

    @staticmethod
    def _find_asset_row(value: str, *, asset_name: str, address: str, org_name: str = "") -> str | None:
        matches: list[str] = []
        for line in value.splitlines():
            match = _ASSET_ROW.match(line)
            if match is None:
                continue
            columns = line.split("|")
            row_org = columns[4].strip() if len(columns) >= 6 else ""
            if match.group("name").strip() == asset_name and match.group("address").strip() == address and (not org_name or row_org == org_name):
                matches.append(match.group("row_id"))
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _find_text_row(value: str, text: str) -> str | None:
        expected = text.casefold()
        for line in value.splitlines():
            match = re.match(r"^\s*(\d+)\s*\|", line)
            if match is not None and expected in line.casefold():
                return match.group(1)
        return None

    @staticmethod
    def _connection_banner(value: str) -> str:
        marker_indexes = [
            index
            for marker in ("开始连接到", "Connecting to")
            if (index := value.rfind(marker)) >= 0
        ]
        return value[max(marker_indexes):] if marker_indexes else value

    @staticmethod
    def _deduplicate(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unique: dict[str, dict[str, Any]] = {}
        for asset in assets:
            unique[str(asset["id"])] = asset
        return list(unique.values())
