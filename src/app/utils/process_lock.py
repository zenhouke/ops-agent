from __future__ import annotations

import os
from pathlib import Path
from typing import IO

from app.utils.secure_storage import ensure_private_file


class ProcessLock:
    """Cross-platform, non-blocking exclusive lock backed by one data-dir file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle: IO[str] | None = None

    def acquire(self) -> bool:
        if self._handle is not None:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="utf-8")
        ensure_private_file(self.path)
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                if self.path.stat().st_size == 0:
                    handle.write("0")
                    handle.flush()
                    handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError):
            handle.close()
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
            self._handle = None

    def __enter__(self) -> ProcessLock:
        if not self.acquire():
            raise RuntimeError(f"Ops Agent data directory is already in use: {self.path.parent}")
        return self

    def __exit__(self, *_: object) -> None:
        self.release()
