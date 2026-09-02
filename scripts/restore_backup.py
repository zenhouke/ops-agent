from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.db.migrations import verify_backup  # noqa: E402
from app.shared.config import APP_DIR, DB_PATH  # noqa: E402
from app.utils.secure_storage import ensure_private_file  # noqa: E402
from app.utils.process_lock import ProcessLock  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore a verified Ops Agent pre-migration backup")
    parser.add_argument("backup_dir", type=Path)
    parser.add_argument("--confirm", action="store_true", help="required before replacing current data")
    args = parser.parse_args()
    backup_dir = args.backup_dir.resolve()
    verify_backup(backup_dir)
    if not args.confirm:
        raise SystemExit("Backup verified. Re-run with --confirm while Ops Agent is stopped to restore it.")
    lock = ProcessLock(APP_DIR / "instance.lock")
    if not lock.acquire():
        raise SystemExit("Refusing restore while Ops Agent is using this data directory")
    try:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=APP_DIR, prefix="restore-", delete=False) as handle:
            temporary_database = Path(handle.name)
            with (backup_dir / "ops_agent.db").open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        ensure_private_file(temporary_database)
        temporary_database.replace(DB_PATH)
        ensure_private_file(DB_PATH)
        for suffix in ("-wal", "-shm"):
            stale = Path(f"{DB_PATH}{suffix}")
            if stale.is_file():
                stale.unlink()
        backup_key = backup_dir / "secret.key"
        if backup_key.is_file():
            with tempfile.NamedTemporaryFile(dir=APP_DIR, prefix="secret-", delete=False) as handle:
                temporary_key = Path(handle.name)
                handle.write(backup_key.read_bytes())
                handle.flush()
                os.fsync(handle.fileno())
            ensure_private_file(temporary_key)
            temporary_key.replace(APP_DIR / "secret.key")
            ensure_private_file(APP_DIR / "secret.key")
    finally:
        lock.release()
    print(f"Restored verified backup from {backup_dir}")


if __name__ == "__main__":
    main()
