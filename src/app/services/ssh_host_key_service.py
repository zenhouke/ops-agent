"""Short-lived confirmations bound to the asset and the observed server key."""
import secrets
import threading
import time

import paramiko

from app.core.connectors.ssh_host_keys import UnknownSSHHostKey, trust_host_key

_pending: dict[str, tuple[int | None, float, str, paramiko.PKey]] = {}
_lock = threading.Lock()


def host_key_challenge(error: Exception, asset_id: int | None) -> dict[str, str] | None:
    cause: BaseException | None = error
    visited: set[int] = set()
    while cause is not None and id(cause) not in visited:
        visited.add(id(cause))
        if isinstance(cause, UnknownSSHHostKey):
            with _lock:
                now = time.monotonic()
                for token, (_, expires, _, _) in list(_pending.items()):
                    if expires <= now:
                        del _pending[token]
                if len(_pending) >= 256:
                    del _pending[next(iter(_pending))]
                token = secrets.token_urlsafe(32)
                _pending[token] = (asset_id, now + 600, cause.hostname, cause.key)
            return {"token": token, "hostname": cause.hostname, "algorithm": cause.key.get_name(), "fingerprint": cause.fingerprint}
        cause = cause.__cause__ or cause.__context__
    return None


def confirm_host_key(asset_id: int | None, token: str) -> None:
    with _lock:
        pending = _pending.get(token)
        if pending is None or pending[0] != asset_id or pending[1] <= time.monotonic():
            raise ValueError("主机指纹确认已过期或不匹配，请重新连接。")
        trust_host_key(pending[2], pending[3])
        del _pending[token]
