from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator


class JumpServerInstanceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    auth_mode: Literal["access_key", "ssh_gateway"] = "access_key"
    base_url: str = Field(min_length=1, max_length=500)
    org_id: str = Field(default="", max_length=64)
    access_key_id: str = Field(default="", max_length=255)
    access_key_secret: SecretStr | None = None
    verify_tls: bool = True
    enabled: bool = True

    @model_validator(mode="after")
    def validate_authentication(self):
        secret = self.access_key_secret.get_secret_value() if self.access_key_secret else ""
        if not self.access_key_id.strip() or not secret:
            label = "SSH username/private key" if self.auth_mode == "ssh_gateway" else "Access Key ID/Secret"
            raise ValueError(f"{label} is required")
        if self.auth_mode == "ssh_gateway" and not self.base_url.startswith("ssh://"):
            raise ValueError("SSH gateway mode requires an ssh:// address")
        if self.auth_mode == "access_key" and not self.base_url.startswith(("http://", "https://")):
            raise ValueError("Access Key mode requires an http:// or https:// address")
        return self

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized.startswith(("http://", "https://", "ssh://")):
            raise ValueError("JumpServer URL must start with http://, https://, or ssh://")
        return normalized


class JumpServerInstanceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    auth_mode: Literal["access_key", "ssh_gateway"] | None = None
    base_url: str | None = Field(default=None, min_length=1, max_length=500)
    org_id: str | None = Field(default=None, max_length=64)
    access_key_id: str | None = Field(default=None, min_length=1, max_length=255)
    access_key_secret: SecretStr | None = None
    verify_tls: bool | None = None
    enabled: bool | None = None

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().rstrip("/")
        if not normalized.startswith(("http://", "https://", "ssh://")):
            raise ValueError("JumpServer URL must start with http://, https://, or ssh://")
        return normalized


class JumpServerInstanceView(BaseModel):
    id: int
    authMode: str
    name: str
    baseUrl: str
    orgId: str
    accessKeyId: str
    accessKeySecretMasked: str
    verifyTls: bool
    enabled: bool
    connectionStatus: str
    lastError: str
    lastSyncAt: str | None
    assetCount: int


class JumpServerOperationView(BaseModel):
    success: bool
    message: str = ""
    created: int = 0
    updated: int = 0
    total: int = 0
    skipped: int = 0


class JumpServerAccountView(BaseModel):
    id: Any = None
    name: Any = None
    username: Any = None
    alias: Any = None
    secret_type: Any = None
    privileged: Any = None
    is_active: Any = None


class JumpServerAssetBindingView(BaseModel):
    id: int
    assetId: int
    externalAssetId: str
    name: str
    address: str
    platform: str
    category: str
    type: str
    accounts: list[JumpServerAccountView]
    accountRef: str
    accountUsername: str
    active: bool


class JumpServerAccountSelection(BaseModel):
    account_ref: str = Field(min_length=1)
