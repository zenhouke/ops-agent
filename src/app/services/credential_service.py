import base64
import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class CredentialService:
    encryption_version = "v2"
    legacy_encryption_version = "v1"
    _associated_data = b"ops-agent:credential:v2"

    def __init__(self, secret_key: str):
        self._key = hashlib.sha256(secret_key.encode("utf-8")).digest()

    def encrypt_secret(self, plaintext: str) -> str:
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._key).encrypt(
            nonce,
            plaintext.encode("utf-8"),
            self._associated_data,
        )
        return base64.b64encode(nonce + ciphertext).decode("ascii")

    def decrypt_secret(self, encrypted_blob: str, encryption_version: str | None = None) -> str:
        version = encryption_version or self.legacy_encryption_version
        raw = base64.b64decode(encrypted_blob.encode("ascii"), validate=True)
        if version == self.encryption_version:
            if len(raw) < 29:
                raise ValueError("Invalid encrypted credential payload")
            try:
                plaintext = AESGCM(self._key).decrypt(
                    raw[:12],
                    raw[12:],
                    self._associated_data,
                )
            except InvalidTag as exc:
                raise ValueError("Credential authentication failed") from exc
            return plaintext.decode("utf-8")
        if version == self.legacy_encryption_version:
            decrypted = bytes(value ^ self._key[index % len(self._key)] for index, value in enumerate(raw))
            return decrypted.decode("utf-8")
        raise ValueError(f"Unsupported credential encryption version: {version}")
