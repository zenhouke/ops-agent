from io import StringIO
from collections.abc import Callable
from typing import Any

from app.core.connectors.network import NetworkConnector
from app.core.connectors.local_pty import LocalPtyConnector
from app.core.connectors.serial import SerialConnector
from app.core.connectors.ssh_proxy import (
    SSHProxyAssetNotFoundError,
    SSHProxyAuthenticationMaterialError,
    SSHProxyChannelOpenError,
    SSHProxyConfig,
    SSHProxyConfigurationError,
    SSHProxyConnectionError,
    SSHProxyUnsupportedTargetError,
    SSHTargetConnectionThroughProxyError,
)


class ServerConnector:
    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str | None = None,
        private_key: str | None = None,
        passphrase: str | None = None,
        proxy_config: SSHProxyConfig | None = None,
        close_callback: Callable[[], None] | None = None,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.private_key = private_key
        self.passphrase = passphrase
        self.proxy_config = proxy_config
        self.close_callback = close_callback
        self._close_callback_called = False
        self.shell_kind = "posix"
        self.client = None
        self.channel = None
        self.proxy_client = None
        self.proxy_channel = None

    def _load_private_key_text(self, private_key: str, passphrase: str | None):
        import paramiko

        key_text = private_key.strip()
        key_stream = StringIO(key_text)
        key_loaders = [paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey]
        last_error = None
        for key_loader in key_loaders:
            key_stream.seek(0)
            try:
                return key_loader.from_private_key(key_stream, password=passphrase or None)
            except Exception as exc:  # noqa: PERF203
                last_error = exc
        raise ValueError("SSH private key format is invalid or passphrase is incorrect") from last_error

    def _load_private_key(self):
        if not self.private_key:
            return None
        return self._load_private_key_text(self.private_key, self.passphrase)

    def _create_ssh_client(self):
        import paramiko

        client = paramiko.SSHClient()
        try:
            client.load_system_host_keys()
        except Exception:
            pass
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        return client

    def _build_connect_kwargs(
        self,
        host: str,
        port: int,
        username: str,
        password: str | None,
        private_key: str | None,
        passphrase: str | None,
        sock=None,
    ) -> dict[str, object]:
        connect_kwargs: dict[str, object] = {
            "hostname": host,
            "port": port,
            "username": username,
            "allow_agent": False,
            "look_for_keys": False,
        }
        if sock is not None:
            connect_kwargs["sock"] = sock
        if private_key:
            connect_kwargs["pkey"] = self._load_private_key_text(private_key, passphrase)
            if passphrase:
                connect_kwargs["passphrase"] = passphrase
            if password is not None:
                connect_kwargs["password"] = password
        elif password is not None:
            connect_kwargs["password"] = password
        else:
            raise ValueError("SSH authentication material is required")
        return connect_kwargs

    def _connect_client(self, client: Any, connect_kwargs: dict[str, object]) -> None:
        client.connect(**connect_kwargs)  # pyright: ignore[reportArgumentType]

    def connect(self) -> None:
        if self.proxy_config is not None:
            self._connect_through_proxy(self.proxy_config)
            return

        client = self._create_ssh_client()
        connect_kwargs = self._build_connect_kwargs(
            self.host,
            self.port,
            self.username,
            self.password,
            self.private_key,
            self.passphrase,
        )
        self._connect_client(client, connect_kwargs)
        transport = client.get_transport()
        if transport is not None:
            transport.set_keepalive(30)
        self.client = client

    def _connect_through_proxy(self, proxy_config: SSHProxyConfig) -> None:
        proxy_client = self._create_ssh_client()
        try:
            self._connect_client(
                proxy_client,
                self._build_connect_kwargs(
                    proxy_config.host,
                    proxy_config.port,
                    proxy_config.username,
                    proxy_config.password,
                    proxy_config.private_key,
                    proxy_config.passphrase,
                ),
            )
        except Exception as exc:
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

        try:
            proxy_channel = transport.open_channel(
                "direct-tcpip",
                (self.host, self.port),
                ("127.0.0.1", 0),
                timeout=15.0,
            )
        except Exception as exc:
            proxy_client.close()
            raise SSHProxyChannelOpenError(
                f"SSH proxy asset {proxy_config.name} could not open a channel to {self.host}:{self.port}."
            ) from exc

        if proxy_channel is None:
            proxy_client.close()
            raise SSHProxyChannelOpenError(
                f"SSH proxy asset {proxy_config.name} could not open a channel to {self.host}:{self.port}."
            )

        target_client = None
        try:
            target_client = self._create_ssh_client()
            self._connect_client(
                target_client,
                self._build_connect_kwargs(
                    self.host,
                    self.port,
                    self.username,
                    self.password,
                    self.private_key,
                    self.passphrase,
                    sock=proxy_channel,
                ),
            )
        except Exception as exc:
            if target_client is not None:
                target_client.close()
            proxy_channel.close()
            proxy_client.close()
            raise SSHTargetConnectionThroughProxyError(
                f"Target SSH connection to {self.host}:{self.port} failed through proxy asset {proxy_config.name}."
            ) from exc

        target_transport = target_client.get_transport()
        if target_transport is not None:
            target_transport.set_keepalive(30)

        self.proxy_client = proxy_client
        self.proxy_channel = proxy_channel
        self.client = target_client

    def run_command(self, command: str) -> str:
        if self.client is None:
            self.connect()
        assert self.client is not None
        _, stdout, _ = self.client.exec_command(command)
        return stdout.read().decode()

    def open_interactive(self) -> object:
        if self.client is None:
            self.connect()
        assert self.client is not None
        self.channel = self.client.invoke_shell(term="xterm-256color")
        return self.channel

    def read(self) -> str:
        if self.channel is None or not self.channel.recv_ready():
            return ""
        return self.channel.recv(4096).decode(errors="ignore")

    def write(self, data: str) -> None:
        if self.channel is not None:
            try:
                self.channel.send(data.encode('utf-8'))
            except Exception:
                pass

    def resize(self, cols: int, rows: int) -> None:
        if self.channel is not None:
            try:
                self.channel.resize_pty(width=cols, height=rows)
            except Exception:
                pass

    def close(self) -> None:
        if self.close_callback is not None and not self._close_callback_called:
            self._close_callback_called = True
            self.close_callback()
        if self.channel is not None:
            self.channel.close()
            self.channel = None
        if self.client is not None:
            self.client.close()
            self.client = None
        if self.proxy_channel is not None:
            self.proxy_channel.close()
            self.proxy_channel = None
        if self.proxy_client is not None:
            self.proxy_client.close()
            self.proxy_client = None


def connector_factory(asset, *, credential_secret_override: str | None = None):
    from sqlmodel import Session

    from app.db.session import engine
    from app.core.connectors.ssh_proxy import (
        SSHProxyAssetNotFoundError,
        SSHProxyAuthenticationMaterialError,
        SSHProxyConfig,
        SSHProxyConfigurationError,
        SSHProxyUnsupportedTargetError,
    )
    from app.services.asset_service import get_asset_credential_record, get_asset_record
    from app.services.credential_service import CredentialService
    from app.services.secret_key import get_ops_agent_secret_key
    from app.services.ssh_key_service import get_ssh_key_record
    from app.core.connectors.device_profiles import netmiko_device_type

    credential_service = CredentialService(secret_key=get_ops_agent_secret_key())
    asset_id = getattr(asset, "id", None)
    asset_type = getattr(asset, "asset_type", "")

    if getattr(asset, "auth_type", "") == "jumpserver":
        from app.services.jumpserver_service import get_jumpserver_service
        with Session(engine) as session:
            connector = get_jumpserver_service().connector_for_asset(session, asset)
        if connector is None:
            raise ValueError("JumpServer asset binding was not found.")
        return connector

    if asset_type == "local_terminal":
        return LocalPtyConnector()

    if asset_type == "serial":
        serial_tags = {
            key: value
            for tag in getattr(asset, "tags", [])
            if ":" in tag
            for key, value in [tag.split(":", 1)]
        }
        parity_mapping = {
            "none": "N",
            "odd": "O",
            "even": "E",
        }
        try:
            bytesize = int(serial_tags.get("data-bits", "8"))
            stopbits = float(serial_tags.get("stop-bits", "1"))
        except ValueError as exc:
            raise ValueError("Invalid serial tag configuration") from exc
        parity = parity_mapping.get(serial_tags.get("parity", "none"), "N")
        return SerialConnector(
            device=getattr(asset, "host"),
            baudrate=int(getattr(asset, "port") or 9600),
            bytesize=bytesize,
            parity=parity,
            stopbits=stopbits,
        )

    password = None
    private_key = None
    passphrase = None
    proxy_config = None

    with Session(engine) as session:
        def resolve_auth_material(current_asset):
            current_asset_id = getattr(current_asset, "id", None)
            current_auth_type = getattr(current_asset, "auth_type", "")
            current_ssh_key_id = getattr(current_asset, "ssh_key_id", None)
            resolved_password = None
            resolved_private_key = None
            resolved_passphrase = None
            is_target_asset = current_asset is asset

            if current_auth_type in {"password", "password_and_key"}:
                credential = None if is_target_asset and credential_secret_override is not None else get_asset_credential_record(session, current_asset_id)
                if credential is None:
                    if is_target_asset and credential_secret_override is not None:
                        resolved_password = credential_secret_override
                    else:
                        raise ValueError(f"Password credential is required for {current_auth_type} auth")
                if credential is not None:
                    resolved_password = credential_service.decrypt_secret(
                        credential.encrypted_blob,
                        credential.encryption_version,
                    )
            if current_auth_type in {"key", "password_and_key"}:
                if current_ssh_key_id is None:
                    raise ValueError("SSH key is required for key auth")
                ssh_key = get_ssh_key_record(session, current_ssh_key_id)
                if ssh_key is None:
                    raise ValueError("SSH key not found")
                resolved_private_key = credential_service.decrypt_secret(
                    ssh_key.encrypted_private_key,
                    ssh_key.private_key_encryption_version,
                )
                if ssh_key.encrypted_passphrase:
                    resolved_passphrase = credential_service.decrypt_secret(
                        ssh_key.encrypted_passphrase,
                        ssh_key.passphrase_encryption_version,
                    )
            elif current_auth_type != "password":
                credential = get_asset_credential_record(session, current_asset_id)
                if credential is not None:
                    resolved_password = credential_service.decrypt_secret(
                        credential.encrypted_blob,
                        credential.encryption_version,
                    )

            if resolved_password is None and resolved_private_key is None:
                raise SSHProxyAuthenticationMaterialError("SSH authentication material is required")
            return resolved_password, resolved_private_key, resolved_passphrase

        password, private_key, passphrase = resolve_auth_material(asset)
        proxy_asset_id = getattr(asset, "proxy_asset_id", None)
        if proxy_asset_id is not None:
            if proxy_asset_id == asset_id:
                raise SSHProxyConfigurationError("Asset cannot use itself as a proxy")
            proxy_target_types = {"linux", "network", "cisco", "huawei", "juniper", "h3c"}
            if asset_type not in proxy_target_types:
                raise SSHProxyUnsupportedTargetError(
                    "SSH proxy is supported only for Linux and network device assets in this version"
                )
            proxy_asset = get_asset_record(session, proxy_asset_id)
            if proxy_asset is None:
                raise SSHProxyAssetNotFoundError("Proxy asset not found")
            if getattr(proxy_asset, "asset_type", None) != "linux":
                raise SSHProxyConfigurationError("Proxy asset must be a Linux asset")
            if getattr(proxy_asset, "proxy_asset_id", None) is not None:
                raise SSHProxyConfigurationError("Proxy chains are not supported")
            proxy_password, proxy_private_key, proxy_passphrase = resolve_auth_material(proxy_asset)
            proxy_config = SSHProxyConfig(
                asset_id=getattr(proxy_asset, "id"),
                name=getattr(proxy_asset, "name"),
                host=getattr(proxy_asset, "host"),
                port=getattr(proxy_asset, "port"),
                username=getattr(proxy_asset, "username"),
                password=proxy_password,
                private_key=proxy_private_key,
                passphrase=proxy_passphrase,
            )

    if asset_type in {"network", "cisco", "huawei", "juniper", "h3c"}:
        device_type = netmiko_device_type(asset_type)
        if device_type is None:
            raise ValueError(f"Unsupported network asset type: {asset_type}")

        device_params = {
            "device_type": device_type,
            "asset_type": asset_type,
            "host": getattr(asset, "host"),
            "port": getattr(asset, "port"),
            "username": getattr(asset, "username"),
            "allow_agent": False,
        }
        ssh_params = {
            "host": getattr(asset, "host"),
            "port": getattr(asset, "port"),
            "username": getattr(asset, "username"),
            "password": password,
            "private_key": private_key,
            "passphrase": passphrase,
            "proxy_config": proxy_config,
        }
        if private_key:
            device_params["use_keys"] = True
            device_params["key_file"] = None
            device_params["pkey"] = ServerConnector(
                host=getattr(asset, "host"),
                port=getattr(asset, "port"),
                username=getattr(asset, "username"),
                private_key=private_key,
                passphrase=passphrase,
            )._load_private_key()
            if passphrase:
                device_params["passphrase"] = passphrase
            if password is not None:
                device_params["password"] = password
        elif password is not None:
            device_params["password"] = password
        else:
            raise ValueError("Network device authentication material is required")
        return NetworkConnector(device_params, ssh_params)

    return ServerConnector(
        host=getattr(asset, "host"),
        port=getattr(asset, "port"),
        username=getattr(asset, "username"),
        password=password,
        private_key=private_key,
        passphrase=passphrase,
        proxy_config=proxy_config,
    )
