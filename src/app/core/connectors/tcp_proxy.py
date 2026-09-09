from __future__ import annotations

import base64
import socket
from dataclasses import dataclass


@dataclass(frozen=True)
class TCPProxyConfig:
    kind: str
    host: str
    port: int
    username: str | None = None
    password: str | None = None


def open_proxy_socket(config: TCPProxyConfig, target_host: str, target_port: int, timeout: float = 15.0) -> socket.socket:
    sock = socket.create_connection((config.host, config.port), timeout=timeout)
    try:
        if config.kind == "http_connect":
            credentials = ""
            if config.username is not None:
                raw = f"{config.username}:{config.password or ''}".encode()
                credentials = f"Proxy-Authorization: Basic {base64.b64encode(raw).decode()}\r\n"
            sock.sendall(f"CONNECT {target_host}:{target_port} HTTP/1.1\r\nHost: {target_host}:{target_port}\r\n{credentials}\r\n".encode())
            response = _read_until_headers(sock).decode("iso-8859-1")
            if not response.startswith("HTTP/") or " 200 " not in response.split("\r\n", 1)[0]:
                raise ConnectionError("HTTP CONNECT proxy rejected the tunnel")
        elif config.kind == "socks5":
            methods = b"\x00" if config.username is None else b"\x02"
            sock.sendall(bytes([5, 1, *methods]))
            if _recv_exact(sock, 2)[1] == 2:
                user = (config.username or "").encode(); password = (config.password or "").encode()
                sock.sendall(bytes([1, len(user)]) + user + bytes([len(password)]) + password)
                if _recv_exact(sock, 2)[1] != 0: raise ConnectionError("SOCKS5 authentication failed")
            host = target_host.encode()
            sock.sendall(bytes([5, 1, 0, 3, len(host)]) + host + target_port.to_bytes(2, "big"))
            reply = _recv_exact(sock, 4)
            if len(reply) != 4 or reply[1] != 0: raise ConnectionError("SOCKS5 proxy rejected the tunnel")
            size = 4 if reply[3] == 1 else 16 if reply[3] == 4 else _recv_exact(sock, 1)[0]
            _recv_exact(sock, size + 2)
        else:
            raise ValueError("Unsupported proxy type")
        return sock
    except Exception:
        sock.close()
        raise


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    received = 0
    while received < size:
        chunk = sock.recv(size - received)
        if not chunk:
            raise ConnectionError("Proxy closed the connection")
        chunks.append(chunk)
        received += len(chunk)
    return b"".join(chunks)


def _read_until_headers(sock: socket.socket) -> bytes:
    data = bytearray()
    while b"\r\n\r\n" not in data and len(data) < 65536:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data.extend(chunk)
    return bytes(data)
