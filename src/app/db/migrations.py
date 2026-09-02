from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.shared.config import APP_DIR, DB_PATH
from app.utils.file_store import atomic_write_json
from app.utils.secure_storage import ensure_private_directory, ensure_private_file


CURRENT_SCHEMA_VERSION = 2
SCHEMA_VERSION_TABLE = "app_schema_version"
BACKUP_RETENTION = 5


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def existing_schema_version() -> tuple[int, bool]:
    if not DB_PATH.exists() or DB_PATH.stat().st_size == 0:
        return 0, False
    with sqlite3.connect(DB_PATH) as connection:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if not tables:
            return 0, False
        if SCHEMA_VERSION_TABLE not in tables:
            return 0, True
        row = connection.execute(
            f"SELECT version FROM {SCHEMA_VERSION_TABLE} ORDER BY version DESC LIMIT 1"
        ).fetchone()
        return (int(row[0]) if row else 0), True


def create_pre_migration_backup(from_version: int, to_version: int) -> Path:
    backup_root = APP_DIR / "backups"
    ensure_private_directory(backup_root)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = backup_root / f"pre-migration-v{from_version}-to-v{to_version}-{timestamp}"
    ensure_private_directory(backup_dir)
    database_backup = backup_dir / "ops_agent.db"
    with sqlite3.connect(DB_PATH) as source, sqlite3.connect(database_backup) as destination:
        source.backup(destination)
    ensure_private_file(database_backup)

    files = {"ops_agent.db": _sha256(database_backup)}
    secret_key = APP_DIR / "secret.key"
    if secret_key.is_file():
        copied_key = backup_dir / "secret.key"
        shutil.copyfile(secret_key, copied_key)
        ensure_private_file(copied_key)
        files["secret.key"] = _sha256(copied_key)
    atomic_write_json(
        backup_dir / "manifest.json",
        {
            "createdAt": datetime.now(UTC).isoformat(),
            "fromVersion": from_version,
            "toVersion": to_version,
            "files": files,
        },
    )
    _prune_old_backups(backup_root)
    return backup_dir


def _prune_old_backups(backup_root: Path) -> None:
    backups = sorted(
        (path for path in backup_root.glob("pre-migration-*") if path.is_dir()),
        key=lambda path: path.name,
        reverse=True,
    )
    for stale in backups[BACKUP_RETENTION:]:
        for child in stale.iterdir():
            if child.is_file() and not child.is_symlink():
                child.unlink()
        stale.rmdir()


def record_schema_version(engine: Engine, version: int) -> None:
    with engine.begin() as connection:
        connection.execute(text(
            f"CREATE TABLE IF NOT EXISTS {SCHEMA_VERSION_TABLE} ("
            "version INTEGER PRIMARY KEY, applied_at VARCHAR NOT NULL)"
        ))
        connection.execute(
            text(
                f"INSERT OR IGNORE INTO {SCHEMA_VERSION_TABLE} (version, applied_at) "
                "VALUES (:version, :applied_at)"
            ),
            {"version": version, "applied_at": datetime.now(UTC).isoformat()},
        )


def verify_backup(backup_dir: Path) -> dict[str, object]:
    manifest_path = backup_dir / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = payload.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("Backup manifest has no files")
    for name, expected_hash in files.items():
        path = backup_dir / str(name)
        if not path.is_file() or _sha256(path) != expected_hash:
            raise ValueError(f"Backup checksum mismatch: {name}")
    with sqlite3.connect(backup_dir / "ops_agent.db") as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
    if not integrity or integrity[0] != "ok":
        raise ValueError("Backup database integrity check failed")
    return payload
