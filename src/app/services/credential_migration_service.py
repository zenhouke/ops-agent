from __future__ import annotations

import os
import json
from collections.abc import Iterable

from sqlmodel import Session, select

from app.db.models import Credential, ModelConfigRecord, SSHKey
from app.db.repositories.models import create_model_config, list_model_configs
from app.services.credential_service import CredentialService
from app.services.secret_key import get_ops_agent_secret_key
from app.shared.config import SETTINGS_PATH
from app.shared.enums import ModelProvider
from app.core.llm.provider_presets import get_default_base_url, get_default_model
from app.utils.file_store import atomic_write_json


def _legacy_decryptors() -> list[CredentialService]:
    keys: list[str] = []
    legacy_key = os.environ.get("OPS_AGENT_LEGACY_SECRET_KEY", "").strip()
    if legacy_key:
        keys.append(legacy_key)
    current_key = get_ops_agent_secret_key()
    if current_key not in keys:
        keys.append(current_key)
    return [CredentialService(key) for key in keys]


def _decrypt_legacy(
    encrypted_blob: str,
    decryptors: Iterable[CredentialService],
    *,
    record_label: str,
) -> str:
    for decryptor in decryptors:
        try:
            return decryptor.decrypt_secret(
                encrypted_blob,
                CredentialService.legacy_encryption_version,
            )
        except (UnicodeDecodeError, ValueError):
            continue
    raise RuntimeError(
        f"Unable to migrate {record_label}; set OPS_AGENT_LEGACY_SECRET_KEY to the key used by v1 data"
    )


def migrate_legacy_credentials(session: Session) -> int:
    encryptor = CredentialService(get_ops_agent_secret_key())
    decryptors = _legacy_decryptors()
    migrated = 0

    try:
        for record in session.exec(select(Credential)).all():
            if record.encryption_version == CredentialService.encryption_version:
                continue
            plaintext = _decrypt_legacy(
                record.encrypted_blob,
                decryptors,
                record_label=f"asset credential {record.id}",
            )
            record.encrypted_blob = encryptor.encrypt_secret(plaintext)
            record.encryption_version = CredentialService.encryption_version
            session.add(record)
            migrated += 1

        for record in session.exec(select(SSHKey)).all():
            if record.private_key_encryption_version != CredentialService.encryption_version:
                plaintext = _decrypt_legacy(
                    record.encrypted_private_key,
                    decryptors,
                    record_label=f"SSH private key {record.id}",
                )
                record.encrypted_private_key = encryptor.encrypt_secret(plaintext)
                record.private_key_encryption_version = CredentialService.encryption_version
                session.add(record)
                migrated += 1
            if (
                record.encrypted_passphrase
                and record.passphrase_encryption_version != CredentialService.encryption_version
            ):
                plaintext = _decrypt_legacy(
                    record.encrypted_passphrase,
                    decryptors,
                    record_label=f"SSH passphrase {record.id}",
                )
                record.encrypted_passphrase = encryptor.encrypt_secret(plaintext)
                record.passphrase_encryption_version = CredentialService.encryption_version
                session.add(record)
                migrated += 1

        for record in session.exec(select(ModelConfigRecord)).all():
            if record.api_key_encryption_version == CredentialService.encryption_version:
                continue
            plaintext = _decrypt_legacy(
                record.encrypted_api_key,
                decryptors,
                record_label=f"model API key {record.id}",
            )
            record.encrypted_api_key = encryptor.encrypt_secret(plaintext)
            record.api_key_encryption_version = CredentialService.encryption_version
            session.add(record)
            migrated += 1

        session.commit()
    except Exception:
        session.rollback()
        raise
    return migrated


def migrate_legacy_model_settings(session: Session) -> bool:
    """Move a legacy plaintext model key into the encrypted model-config table."""
    if not SETTINGS_PATH.exists():
        return False
    payload = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Legacy settings must contain a JSON object")
    api_key = payload.pop("api_key", None)
    if not isinstance(api_key, str) or not api_key:
        return False

    if not list_model_configs(session):
        provider = ModelProvider(payload.get("provider", ModelProvider.OPENAI_COMPATIBLE.value))
        credential_service = CredentialService(get_ops_agent_secret_key())
        create_model_config(
            session,
            name="Migrated default",
            provider=provider.value,
            base_url=str(payload.get("base_url") or get_default_base_url(provider)),
            api_key_encryption_version=CredentialService.encryption_version,
            encrypted_api_key=credential_service.encrypt_secret(api_key),
            model_name=str(payload.get("model_name") or get_default_model(provider)),
            is_default=True,
            timeout_seconds=int(payload.get("timeout_seconds", 30)),
            temperature=float(payload.get("temperature", 0.2)),
            max_tokens=int(payload.get("max_tokens", 1024)),
            description="Migrated from legacy plaintext settings",
        )
    atomic_write_json(SETTINGS_PATH, payload)
    return True
