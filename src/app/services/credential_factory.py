from app.services.credential_service import CredentialService
from app.shared.secret_key import get_ops_agent_secret_key


def build_credential_service() -> CredentialService:
    return CredentialService(secret_key=get_ops_agent_secret_key())
