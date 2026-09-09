import json
import os
import tempfile
from pathlib import Path
from typing import Any

from app.utils.secure_storage import ensure_private_directory, ensure_private_file


def atomic_write_text(path: Path, text: str) -> None:
    ensure_private_directory(path.parent)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f"{path.stem}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
        ensure_private_file(path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_text(
        path,
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n",
    )
