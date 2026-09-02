from __future__ import annotations

import os
from pathlib import Path


def ensure_private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        path.chmod(0o700)


def ensure_private_file(path: Path) -> None:
    if path.exists() and os.name != "nt":
        path.chmod(0o600)


def harden_storage_tree(root: Path) -> None:
    ensure_private_directory(root)
    if os.name == "nt":
        return
    for path in root.rglob("*"):
        if path.is_symlink():
            continue
        path.chmod(0o700 if path.is_dir() else 0o600)
