import os
import secrets
from pathlib import Path


def _desktop_secret_key() -> str:
    data_dir = Path(os.environ["OPS_AGENT_DATA_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)
    key_path = data_dir / "secret.key"
    if key_path.exists():
        secret_key = key_path.read_text(encoding="utf-8").strip()
        if secret_key:
            return secret_key
    secret_key = secrets.token_urlsafe(48)
    file_descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(file_descriptor, "w", encoding="utf-8") as key_file:
        key_file.write(secret_key)
    return secret_key


def get_ops_agent_secret_key() -> str:
    secret_key = os.environ.get("OPS_AGENT_SECRET_KEY", "").strip()
    if secret_key:
        return secret_key
    if os.environ.get("OPS_AGENT_DESKTOP") == "true" and os.environ.get("OPS_AGENT_DATA_DIR"):
        return _desktop_secret_key()
    if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("OPS_AGENT_ENV") in {"dev", "test"}:
        return "dev-secret-key"
    raise RuntimeError("OPS_AGENT_SECRET_KEY must be set")
