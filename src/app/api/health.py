from fastapi import APIRouter, HTTPException
from sqlmodel import Session, select

from app.db.models import Credential, ModelConfigRecord, SSHKey
from app.db.session import engine
from app.services.credential_service import CredentialService
from app.services.model_service import ModelService
from app.utils.credential_factory import build_credential_service
from app.build_metadata import BUILD_SHA, VERSION

router = APIRouter()


@router.get("/health")
def health() -> dict[str, object]:
    return {"ok": True, "version": VERSION, "buildSha": BUILD_SHA}


@router.get("/ready")
def readiness() -> dict[str, object]:
    credential_service = build_credential_service()
    try:
        with Session(engine) as session:
            for record in session.exec(select(Credential)).all():
                credential_service.decrypt_secret(record.encrypted_blob, record.encryption_version)
            for record in session.exec(select(SSHKey)).all():
                credential_service.decrypt_secret(
                    record.encrypted_private_key,
                    record.private_key_encryption_version,
                )
                if record.encrypted_passphrase:
                    credential_service.decrypt_secret(
                        record.encrypted_passphrase,
                        record.passphrase_encryption_version,
                    )
            for record in session.exec(select(ModelConfigRecord)).all():
                ModelService().decrypt_api_key(record)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Credential store is not ready") from exc
    return {
        "ready": True,
        "credentialEncryptionV2": True,
        "version": VERSION,
        "buildSha": BUILD_SHA,
    }
