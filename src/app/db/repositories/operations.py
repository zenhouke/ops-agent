from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.utils.file_store import atomic_write_json


class OperationRepository:
    def __init__(self, directory: Path):
        self.directory = directory

    def list(self) -> list[dict[str, Any]]:
        if not self.directory.exists():
            return []
        return [json.loads(path.read_text(encoding="utf-8")) for path in self.directory.glob("op_*.json")]

    def save(self, operation: dict[str, Any]) -> None:
        atomic_write_json(self.directory / f"{operation['id']}.json", operation)
