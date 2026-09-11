from io import StringIO
from collections.abc import Callable
from typing import Any

from app.core.connectors.ssh_host_keys import configure_strict_ssh_client
from app.core.connectors.ssh_proxy import (
    SSHProxyAuthenticationMaterialError,
    SSHProxyChannelOpenError,
    SSHProxyConfig,
    SSHProxyConfigurationError,
    SSHProxyConnectionError,
    SSHTargetConnectionThroughProxyError,
)
from app.core.connectors.tcp_proxy import TCPProxyConfig, open_proxy_socket


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
        tcp_proxy_config: TCPProxyConfig | None = None,
        close_callback: Callable[[], None] | None = None,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.private_key = private_key
        self.passphrase = passphrase
        self.proxy_config = proxy_config
        self.tcp_proxy_config = tcp_proxy_config
        self.close_callback = close_callback
        self._close_callback_called = False
        self.shell_kind = "posix"
        self.client = None
        self.channel = None
        self.proxy_client = None
        self.proxy_channel = None
        self.tcp_proxy_socket = None

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
        return configure_strict_ssh_client(client)

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
        if self.tcp_proxy_config is not None:
            self.tcp_proxy_socket = open_proxy_socket(self.tcp_proxy_config, self.host, self.port)
        connect_kwargs = self._build_connect_kwargs(
            self.host,
            self.port,
            self.username,
            self.password,
            self.private_key,
            self.passphrase,
        )
        if self.tcp_proxy_socket is not None:
            connect_kwargs["sock"] = self.tcp_proxy_socket
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
        if self.tcp_proxy_socket is not None:
            self.tcp_proxy_socket.close()
            self.tcp_proxy_socket = None
