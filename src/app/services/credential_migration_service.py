from __future__ import annotations

import os
from collections.abc import Iterable

from sqlmodel import Session, select

from app.db.models import Credential, ModelConfigRecord, SSHKey
from app.services.credential_service import CredentialService
from app.services.secret_key import get_ops_agent_secret_key


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
