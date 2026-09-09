from __future__ import annotations

import argparse
import os
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def _free_port() -> int:
    for _ in range(32):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = int(sock.getsockname()[1])
        if port >= 30_000:
            return port
    raise RuntimeError("Unable to allocate a test port above 30000")


def _status(url: str, token: str | None = None, *, method: str = "GET") -> int:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    request = urllib.request.Request(url, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("binary", type=Path)
    args = parser.parse_args()
    binary = args.binary.resolve()
    if not binary.is_file():
        raise SystemExit(f"Backend binary not found: {binary}")
    port = _free_port()
    token = "backend-smoke-token"
    with tempfile.TemporaryDirectory(prefix="ops-agent-smoke-") as data_dir:
        env = {
            **os.environ,
            "OPS_AGENT_DATA_DIR": data_dir,
            "OPS_AGENT_BACKEND_PORT": str(port),
            "OPS_AGENT_RELOAD": "false",
            "OPS_AGENT_AUTH_DISABLED": "false",
            "OPS_AGENT_API_TOKEN": token,
            "OPS_AGENT_SECRET_KEY": "backend-smoke-secret",
        }
        process = subprocess.Popen([str(binary)], env=env)
        try:
            base_url = f"http://127.0.0.1:{port}"
            for _ in range(80):
                if process.poll() is not None:
                    raise RuntimeError(f"Backend exited early with code {process.returncode}")
                try:
                    if _status(f"{base_url}/ready") == 200:
                        break
                except OSError:
                    pass
                time.sleep(0.25)
            else:
                raise RuntimeError("Backend did not become ready")
            assert _status(f"{base_url}/api/auth/verify", method="POST") == 401
            assert _status(f"{base_url}/api/auth/verify", token, method="POST") == 204
            assert _status(f"{base_url}/api/assets", token) == 200
            print("Packaged backend smoke test passed")
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
