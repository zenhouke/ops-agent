from app.db.repositories.ssh_keys import create_ssh_key, delete_ssh_key, get_ssh_key, list_ssh_keys, update_ssh_key
from app.services.credential_factory import build_credential_service
from app.services.credential_service import CredentialService



def create_ssh_key_record(session, payload):
    credential_service = build_credential_service()
    encrypted_private_key = credential_service.encrypt_secret(payload.private_key.get_secret_value())
    encrypted_passphrase = credential_service.encrypt_secret(payload.passphrase.get_secret_value()) if payload.passphrase is not None else None
    return create_ssh_key(
        session,
        name=payload.name,
        public_key=payload.public_key,
        private_key_encryption_version=CredentialService.encryption_version,
        encrypted_private_key=encrypted_private_key,
        passphrase_encryption_version=CredentialService.encryption_version if encrypted_passphrase is not None else None,
        encrypted_passphrase=encrypted_passphrase,
    )


def list_ssh_key_records(session):
    return list_ssh_keys(session)


def get_ssh_key_record(session, ssh_key_id: int):
    return get_ssh_key(session, ssh_key_id)


def update_ssh_key_record(session, ssh_key_id: int, payload):
    updates = payload.model_dump(exclude_unset=True, exclude={"private_key", "passphrase", "clear_passphrase"})
    credential_service = build_credential_service()
    if payload.private_key is not None:
        updates["private_key_encryption_version"] = CredentialService.encryption_version
        updates["encrypted_private_key"] = credential_service.encrypt_secret(payload.private_key.get_secret_value())
    if payload.clear_passphrase:
        updates["passphrase_encryption_version"] = None
        updates["encrypted_passphrase"] = None
    elif payload.passphrase is not None:
        updates["passphrase_encryption_version"] = CredentialService.encryption_version
        updates["encrypted_passphrase"] = credential_service.encrypt_secret(payload.passphrase.get_secret_value())
    return update_ssh_key(session, ssh_key_id, **updates)


def delete_ssh_key_record(session, ssh_key_id: int) -> bool:
    return delete_ssh_key(session, ssh_key_id)
