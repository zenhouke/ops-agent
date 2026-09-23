"""Persistence port used by the live Agent runtime."""
from typing import Any, Protocol


class RuntimeStore(Protocol):
    def save_snapshot(self, snapshot: dict[str, Any], *, run_state: str) -> None:
        ...

    def append_event(self, snapshot: dict[str, Any], event: dict[str, Any], *, run_state: str) -> None:
        ...

    def get_snapshot(self, runtime_id: str) -> dict[str, Any] | None:
        ...

    def list_snapshots(self, conversation_id: str, *, limit: int=100) -> list[dict[str, Any]]:
        ...

    def events_since(self, runtime_id: str, since: int) -> tuple[int, list[dict[str, Any]]]:
        ...

    def recover_interrupted(self) -> int:
        ...

    def prune(self, *, retention_days: int=30) -> int:
        ...
