from collections.abc import Iterable
from io import StringIO
from typing import Any, cast

from netmiko import ConnectHandler, SSHDetect
from netmiko.exceptions import ReadTimeout

from app.core.connectors.device_profiles import (
    NETWORK_CLI_PROFILE,
    GENERIC_DEVICE_PROFILE,
    asset_type_for_netmiko_device_type,
    matches_command_prefix,
    select_device_profile,
)
from app.core.connectors.execution import ExecutionContext, ExecutionEvent, ExecutionResult
from app.core.connectors.network_collection import (
    NetworkCollectionKind,
    collection_commands,
    normalize_collection_record,
)
from app.core.connectors.network_cli import analyze_transcript, detect_mode, strip_pager_markers
from app.core.connectors.ssh_proxy import (
    SSHProxyChannelOpenError,
    SSHProxyConfig,
    SSHProxyConnectionError,
    SSHTargetConnectionThroughProxyError,
)


class NetworkConnector:
    def __init__(self, device_params: dict[str, Any], ssh_params: dict[str, Any] | None = None):
        self.asset_type = str(device_params.get("asset_type", "") or "")
        netmiko_params = {key: value for key, value in device_params.items() if key != "asset_type"}
        self.device_params = {"conn_timeout": 15, **netmiko_params}
        self.ssh_params = ssh_params or self._build_ssh_params(device_params)
        self.shell_kind = "network"
        self.detected_device_type: str | None = None
        self.connection: Any | None = None
        self.ssh_client: Any | None = None
        self.channel: Any | None = None
        self.netmiko_proxy_client: Any | None = None
        self.netmiko_proxy_channel: Any | None = None
        self.ssh_proxy_client: Any | None = None
        self.ssh_proxy_channel: Any | None = None
        self._execution_events: dict[str, list[ExecutionEvent]] = {}
        self._execution_results: dict[str, ExecutionResult] = {}

    def connect(self) -> None:
        proxy_config = self.ssh_params.get("proxy_config")
        narrowed_proxy = cast(SSHProxyConfig, proxy_config) if proxy_config is not None else None
        try:
            connect_params = dict(self.device_params)
            if connect_params.get("device_type") == "autodetect":
                detect_params = self._with_netmiko_proxy(connect_params, narrowed_proxy)
                detector = SSHDetect(**detect_params)
                detected_device_type = detector.autodetect()
                self._release_netmiko_proxy()
                if not detected_device_type:
                    raise ValueError(
                        "Unable to detect the network device driver. Select an explicit vendor in asset settings."
                    )
                self.detected_device_type = detected_device_type
                connect_params["device_type"] = detected_device_type
            self.connection = ConnectHandler(**self._with_netmiko_proxy(connect_params, narrowed_proxy))
            self._enable_keepalive(self.connection)
        except TypeError as exc:
            self.close()
            if narrowed_proxy is None:
                raise
            raise SSHTargetConnectionThroughProxyError(
                "Netmiko driver does not accept a proxy socket for this network device type."
            ) from exc
        except Exception as exc:
            if narrowed_proxy is None:
                self.close()
                raise
            host = self.ssh_params.get("host")
            port = self.ssh_params.get("port", 22)
            self.close()
            raise SSHTargetConnectionThroughProxyError(
                f"Network device connection to {host}:{port} failed through proxy asset {narrowed_proxy.name}."
            ) from exc

    def run_command(self, command: str) -> str:
        if self.connection is None:
            self.connect()
        connection = self.connection
        assert connection is not None
        return cast(str, connection.send_command(command))

    def connection_facts(self) -> dict[str, str]:
        if self.connection is None:
            self.connect()
        return {
            "deviceType": self.detected_device_type or str(self.device_params.get("device_type", "")),
            "assetType": self._resolve_asset_type(),
            "prompt": self._safe_find_prompt() or "",
        }

    def collect_structured(self, kind: NetworkCollectionKind, *, read_timeout: float = 30.0) -> dict[str, Any]:
        plan = self.collection_plan(kind)
        connection = self.connection
        assert connection is not None
        vendor = str(plan["vendor"])
        commands = collection_commands(vendor, kind)
        records: list[dict[str, Any]] = []
        sources: list[dict[str, Any]] = []
        for spec in commands:
            response = connection.send_command(spec.command, use_textfsm=True, read_timeout=read_timeout)
            parsed = isinstance(response, list) and all(isinstance(item, dict) for item in response)
            if parsed:
                command_records = [
                    normalize_collection_record(kind, cast(dict[str, Any], item), protocol=spec.protocol)
                    for item in response
                ]
                records.extend(command_records)
                sources.append({"command": spec.command, "protocol": spec.protocol, "parsed": True, "recordCount": len(command_records)})
            else:
                raw = str(response)
                analysis = analyze_transcript(raw, select_device_profile(self._resolve_asset_type(), self.shell_kind) or GENERIC_DEVICE_PROFILE)
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
            "vendor": vendor,
            "deviceType": self.detected_device_type or str(self.device_params.get("device_type", "")),
            "records": records,
            "sources": sources,
        }

    def collection_plan(self, kind: NetworkCollectionKind) -> dict[str, Any]:
        if self.connection is None:
            self.connect()
        vendor = (select_device_profile(self._resolve_asset_type(), self.shell_kind) or GENERIC_DEVICE_PROFILE).vendor
        commands = collection_commands(vendor, kind)
        return {
            "vendor": vendor,
            "deviceType": self.detected_device_type or str(self.device_params.get("device_type", "")),
            "commands": [{"command": item.command, "protocol": item.protocol} for item in commands],
        }

    def start_execution(self, command: str, context: ExecutionContext, execution_id: str) -> None:
        profile = select_device_profile(self._resolve_asset_type(), self.shell_kind) or GENERIC_DEVICE_PROFILE
        prompt_before = self._safe_find_prompt()
        normalized_command = command.strip().lower()
        is_read_only = any(matches_command_prefix(prefix, normalized_command) for prefix in profile.read_prefixes)
        read_timeout = context.timeout_seconds or cast(float, self.device_params.get("read_timeout", 30))
        timed_out = False
        timeout_recovered_prompt = None
        try:
            transcript = self._send_command(
                command,
                profile,
                auto_advance_pager=is_read_only,
                read_timeout=read_timeout,
            )
        except ReadTimeout as exc:
            timed_out = True
            transcript = f"Network command timed out after {read_timeout:g} seconds."
            recovery_output, timeout_recovered_prompt = self._recover_cli(read_timeout=min(read_timeout, 5.0))
            if recovery_output:
                transcript = f"{transcript}\n{recovery_output}"
        analysis = analyze_transcript(transcript, profile)
        pager_detected = analysis.pager_detected

        if analysis.pager_detected and is_read_only:
            transcript = strip_pager_markers(transcript, profile)
            analysis = analyze_transcript(transcript, profile)

        confirmation_detected = analysis.confirm_detected
        recovered_prompt = None
        if confirmation_detected:
            recovery_output, recovered_prompt = self._recover_cli(read_timeout=min(read_timeout, 5.0))
            if recovery_output:
                transcript = f"{transcript}{recovery_output}"
        prompt_after = recovered_prompt or timeout_recovered_prompt or (None if timed_out else self._safe_find_prompt()) or analysis.prompt
        needs_attention = timed_out or confirmation_detected or (analysis.pager_detected and not is_read_only)
        completed = prompt_after is not None
        success = completed and analysis.matched_error is None and not needs_attention
        completion_reason = "prompt_detected"
        if pager_detected:
            completion_reason = "pager_end"
        if timed_out or (needs_attention and prompt_after is None):
            completion_reason = "timeout"
        if analysis.matched_error is not None:
            success = False
            needs_attention = True

        result = ExecutionResult(
            execution_id=execution_id,
            output=transcript,
            completed=completed,
            success=success,
            needs_attention=needs_attention or analysis.prompt is None,
            exit_code=None,
            completion_reason=completion_reason,
            mode=detect_mode(prompt_after),
            pager_detected=pager_detected,
            profile=NETWORK_CLI_PROFILE,
            prompt_before=prompt_before,
            prompt_after=prompt_after,
            matched_error=analysis.matched_error,
        )
        self._execution_results[execution_id] = result
        self._execution_events[execution_id] = [
            ExecutionEvent(execution_id=execution_id, event_type="started", profile=NETWORK_CLI_PROFILE, prompt_before=prompt_before),
            ExecutionEvent(execution_id=execution_id, event_type="output", text=transcript, profile=NETWORK_CLI_PROFILE),
            ExecutionEvent(
                execution_id=execution_id,
                event_type="completed",
                text=transcript,
                completed=result.completed,
                success=result.success,
                needs_attention=result.needs_attention,
                exit_code=result.exit_code,
                completion_reason=result.completion_reason,
                mode=result.mode,
                pager_detected=result.pager_detected,
                profile=result.profile,
                prompt_before=result.prompt_before,
                prompt_after=result.prompt_after,
                matched_error=result.matched_error,
            ),
        ]

    def read_execution_events(self, execution_id: str) -> Iterable[ExecutionEvent]:
        return list(self._execution_events.get(execution_id, []))

    def get_execution_result(self, execution_id: str) -> ExecutionResult:
        result = self._execution_results.get(execution_id)
        if result is None:
            return ExecutionResult(
                execution_id=execution_id,
                output="",
                completed=False,
                success=False,
                needs_attention=True,
                completion_reason="unsupported",
                profile=NETWORK_CLI_PROFILE,
            )
        return result

    def open_interactive(self) -> object:
        if self.channel is None:
            self._connect_ssh()
        assert self.channel is not None
        return self.channel

    def read(self) -> str:
        if self.channel is None or not self.channel.recv_ready():
            return ""
        return cast(bytes, self.channel.recv(4096)).decode(errors="ignore")

    def write(self, data: str) -> None:
        if self.channel is None:
            return
        self.channel.send(data.encode("utf-8", errors="ignore"))

    def resize(self, cols: int, rows: int) -> None:
        if self.channel is None:
            return
        try:
            self.channel.resize_pty(width=cols, height=rows)
        except Exception:
            pass

    def close(self) -> None:
        if self.channel is not None:
            self.channel.close()
            self.channel = None
        if self.ssh_client is not None:
            self.ssh_client.close()
            self.ssh_client = None
        if self.connection is not None:
            self.connection.disconnect()
            self.connection = None
        if self.netmiko_proxy_channel is not None:
            self.netmiko_proxy_channel.close()
            self.netmiko_proxy_channel = None
        if self.netmiko_proxy_client is not None:
            self.netmiko_proxy_client.close()
            self.netmiko_proxy_client = None
        if self.ssh_proxy_channel is not None:
            self.ssh_proxy_channel.close()
            self.ssh_proxy_channel = None
        if self.ssh_proxy_client is not None:
            self.ssh_proxy_client.close()
            self.ssh_proxy_client = None
        self._execution_events.clear()
        self._execution_results.clear()

    def _connect_ssh(self) -> None:
        proxy_config = self.ssh_params.get("proxy_config")
        narrowed_proxy_config: SSHProxyConfig | None = None
        sock = None
        if proxy_config is not None:
            if not isinstance(proxy_config, SSHProxyConfig):
                raise ValueError("SSH proxy configuration is invalid")
            narrowed_proxy_config = proxy_config
            sock = self._open_proxy_channel(narrowed_proxy_config, kind="ssh")

        client = None
        try:
            client = self._create_ssh_client()
            client.connect(**self._build_paramiko_connect_kwargs(sock=sock))
            transport = client.get_transport()
            if transport is not None:
                transport.set_keepalive(30)
            self.channel = client.invoke_shell(term="xterm-256color")
        except Exception as exc:
            if client is not None:
                client.close()
            if narrowed_proxy_config is not None:
                self.close()
                raise SSHTargetConnectionThroughProxyError(
                    f"Network device connection to {self.ssh_params.get('host')}:{self.ssh_params.get('port', 22)} failed through proxy asset {narrowed_proxy_config.name}."
                ) from exc
            raise
        self.ssh_client = client

    def _create_ssh_client(self) -> Any:
        import paramiko

        client = paramiko.SSHClient()
        try:
            client.load_system_host_keys()
        except Exception:
            pass
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        return client

    def _build_paramiko_connect_kwargs(self, *, sock: Any | None = None) -> dict[str, object]:
        connect_timeout = float(self.device_params.get("conn_timeout", 15))
        connect_kwargs: dict[str, object] = {
            "hostname": self.ssh_params.get("host"),
            "port": self.ssh_params.get("port", 22),
            "username": self.ssh_params.get("username"),
            "allow_agent": False,
            "look_for_keys": False,
            "timeout": connect_timeout,
            "banner_timeout": connect_timeout,
            "auth_timeout": connect_timeout,
            "channel_timeout": connect_timeout,
        }
        if sock is not None:
            connect_kwargs["sock"] = sock
        private_key = self.ssh_params.get("private_key")
        password = self.ssh_params.get("password")
        passphrase = self.ssh_params.get("passphrase")
        if private_key:
            connect_kwargs["pkey"] = self._load_private_key(str(private_key), str(passphrase) if passphrase else None)
            if passphrase:
                connect_kwargs["passphrase"] = passphrase
            if password is not None:
                connect_kwargs["password"] = password
        elif password is not None:
            connect_kwargs["password"] = password
        else:
            raise ValueError("Network device authentication material is required")
        return connect_kwargs

    def _open_proxy_channel(self, proxy_config: SSHProxyConfig, kind: str) -> Any:
        proxy_client = None
        proxy_channel = None
        try:
            proxy_client = self._create_ssh_client()
            proxy_client.connect(**self._build_proxy_connect_kwargs(proxy_config))
        except Exception as exc:
            if proxy_client is not None:
                proxy_client.close()
            raise SSHProxyConnectionError(
                f"Failed to connect to SSH proxy asset {proxy_config.name} ({proxy_config.host}:{proxy_config.port})."
            ) from exc

        transport = proxy_client.get_transport()
        if transport is None:
            proxy_client.close()
            raise SSHProxyChannelOpenError(
                f"SSH proxy asset {proxy_config.name} did not provide an SSH transport."
            )
        transport.set_keepalive(30)

        host = self.ssh_params.get("host")
        port = self.ssh_params.get("port", 22)
        try:
            proxy_channel = transport.open_channel(
                "direct-tcpip",
                (host, port),
                ("127.0.0.1", 0),
                timeout=15.0,
            )
        except Exception as exc:
            proxy_client.close()
            raise SSHProxyChannelOpenError(
                f"SSH proxy asset {proxy_config.name} could not open a channel to {host}:{port}."
            ) from exc

        if proxy_channel is None:
            proxy_client.close()
            raise SSHProxyChannelOpenError(
                f"SSH proxy asset {proxy_config.name} could not open a channel to {host}:{port}."
            )

        if kind == "netmiko":
            if self.netmiko_proxy_channel is not None:
                self.netmiko_proxy_channel.close()
            if self.netmiko_proxy_client is not None:
                self.netmiko_proxy_client.close()
            self.netmiko_proxy_client = proxy_client
            self.netmiko_proxy_channel = proxy_channel
        else:
            if self.ssh_proxy_channel is not None:
                self.ssh_proxy_channel.close()
            if self.ssh_proxy_client is not None:
                self.ssh_proxy_client.close()
            self.ssh_proxy_client = proxy_client
            self.ssh_proxy_channel = proxy_channel

        return proxy_channel

    def _build_proxy_connect_kwargs(self, proxy_config: SSHProxyConfig) -> dict[str, object]:
        connect_timeout = float(self.device_params.get("conn_timeout", 15))
        connect_kwargs: dict[str, object] = {
            "hostname": proxy_config.host,
            "port": proxy_config.port,
            "username": proxy_config.username,
            "allow_agent": False,
            "look_for_keys": False,
            "timeout": connect_timeout,
            "banner_timeout": connect_timeout,
            "auth_timeout": connect_timeout,
            "channel_timeout": connect_timeout,
        }
        if proxy_config.private_key:
            connect_kwargs["pkey"] = self._load_private_key(proxy_config.private_key, proxy_config.passphrase)
            if proxy_config.passphrase:
                connect_kwargs["passphrase"] = proxy_config.passphrase
            if proxy_config.password is not None:
                connect_kwargs["password"] = proxy_config.password
        elif proxy_config.password is not None:
            connect_kwargs["password"] = proxy_config.password
        else:
            raise ValueError("SSH proxy authentication material is required")
        return connect_kwargs

    def _load_private_key(self, private_key: str, passphrase: str | None) -> object:
        import paramiko

        key_stream = StringIO(private_key.strip())
        key_loaders = [paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey]
        last_error = None
        for key_loader in key_loaders:
            key_stream.seek(0)
            try:
                return key_loader.from_private_key(key_stream, password=passphrase or None)
            except Exception as exc:
                last_error = exc
        raise ValueError("SSH private key format is invalid or passphrase is incorrect") from last_error

    def _build_ssh_params(self, device_params: dict[str, Any]) -> dict[str, Any]:
        return {
            "host": device_params.get("host"),
            "port": device_params.get("port", 22),
            "username": device_params.get("username"),
            "password": device_params.get("password"),
        }

    def _send_command(
        self,
        command: str,
        profile,
        *,
        auto_advance_pager: bool = False,
        read_timeout: float | None = None,
    ) -> str:
        if self.connection is None:
            self.connect()
        connection = self.connection
        assert connection is not None
        effective_read_timeout = read_timeout or cast(float, self.device_params.get("read_timeout", 30))
        transcript = cast(
            str,
            connection.send_command_timing(
                command,
                strip_prompt=False,
                strip_command=False,
                cmd_verify=False,
                read_timeout=effective_read_timeout,
            ),
        )
        if not auto_advance_pager:
            return transcript

        latest_chunk = transcript
        for _ in range(int(self.device_params.get("max_pager_advances", 100))):
            analysis = analyze_transcript(latest_chunk, profile)
            if not analysis.pager_detected or analysis.confirm_detected:
                break
            connection.write_channel(" ")
            latest_chunk = cast(
                str,
                connection.read_channel_timing(read_timeout=effective_read_timeout),
            )
            transcript += latest_chunk
        return transcript

    def _recover_cli(self, *, read_timeout: float) -> tuple[str, str | None]:
        connection = self.connection
        if connection is None:
            return "", None
        output = ""
        try:
            connection.write_channel("\x03")
            output = cast(str, connection.read_channel_timing(read_timeout=read_timeout))
        except Exception:
            pass
        return output, self._safe_find_prompt()

    def _with_netmiko_proxy(
        self,
        params: dict[str, Any],
        proxy_config: SSHProxyConfig | None,
    ) -> dict[str, Any]:
        if proxy_config is None:
            return params
        channel = self._open_proxy_channel(proxy_config, kind="netmiko")
        return {**params, "sock": channel}

    def _release_netmiko_proxy(self) -> None:
        if self.netmiko_proxy_channel is not None:
            self.netmiko_proxy_channel.close()
            self.netmiko_proxy_channel = None
        if self.netmiko_proxy_client is not None:
            self.netmiko_proxy_client.close()
            self.netmiko_proxy_client = None

    def _enable_keepalive(self, connection: Any) -> None:
        remote_conn = getattr(connection, "remote_conn", None)
        transport = remote_conn.get_transport() if remote_conn is not None and hasattr(remote_conn, "get_transport") else None
        if transport is not None:
            transport.set_keepalive(30)

    def _safe_find_prompt(self) -> str | None:
        if self.connection is None:
            self.connect()
        connection = self.connection
        assert connection is not None
        try:
            return cast(str, connection.find_prompt())
        except Exception:
            return None

    def _resolve_asset_type(self) -> str:
        if self.asset_type and self.asset_type != "network":
            return self.asset_type
        if self.detected_device_type:
            return asset_type_for_netmiko_device_type(self.detected_device_type)
        device_type = str(self.device_params.get("device_type", "") or "").lower()
        if "cisco" in device_type:
            return "cisco"
        if "juniper" in device_type:
            return "juniper"
        if "huawei" in device_type:
            return "huawei"
        return "network"
