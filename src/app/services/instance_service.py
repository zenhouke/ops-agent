from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class InstanceInfo:
    instance_id: str
    hostname: str
    pid: int
    started_at: datetime
    explicitly_configured: bool

    def as_payload(self) -> dict[str, object]:
        return {
            "instanceId": self.instance_id,
            "hostname": self.hostname,
            "pid": self.pid,
            "startedAt": self.started_at.isoformat(),
            "explicitlyConfigured": self.explicitly_configured,
        }


def _build_instance_info() -> InstanceInfo:
    hostname = socket.gethostname()
    configured_id = os.getenv("OPS_AGENT_INSTANCE_ID", "").strip()
    return InstanceInfo(
        instance_id=configured_id or hostname,
        hostname=hostname,
        pid=os.getpid(),
        started_at=datetime.now(UTC),
        explicitly_configured=bool(configured_id),
    )


_instance_info = _build_instance_info()


def get_instance_info() -> InstanceInfo:
    return _instance_info
