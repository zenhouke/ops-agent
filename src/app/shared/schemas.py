from typing import Any, Literal

from pydantic import BaseModel, Field, SecretStr, model_validator

from app.shared.enums import AssetType, ModelProvider


class AssetCreate(BaseModel):
    name: str
    asset_type: AssetType
    group_id: int | None = None
    ssh_key_id: int | None = None
    proxy_asset_id: int | None = None
    host: str = ""
    port: int = 22
    username: str = ""
    auth_type: str = ""
    credential_secret: SecretStr | None = None
    tags: list[str] = Field(default_factory=list)
    vendor: str = ""
    description: str = ""

    @model_validator(mode="after")
    def validate_connection_fields(self):
        if self.asset_type is AssetType.LOCAL_TERMINAL:
            if self.proxy_asset_id is not None:
                raise ValueError("proxy_asset_id is not supported for local terminal assets")
            return self
        if not self.host:
            raise ValueError("host is required for remote assets")
        if self.asset_type is AssetType.SERIAL:
            if self.proxy_asset_id is not None:
                raise ValueError("proxy_asset_id is not supported for serial assets")
            if self.port <= 0 or self.port == 22:
                raise ValueError("port must be an explicit positive baud rate for serial assets")
            return self
        if not self.username:
            raise ValueError("username is required for remote assets")
        if not self.auth_type:
            raise ValueError("auth_type is required for remote assets")
        return self


class SSHKeyCreate(BaseModel):
    name: str
    public_key: str = ""
    private_key: SecretStr
    passphrase: SecretStr | None = None


class SSHKeyUpdate(BaseModel):
    name: str | None = None
    public_key: str | None = None
    private_key: SecretStr | None = None
    passphrase: SecretStr | None = None
    clear_passphrase: bool = False


class ModelConfig(BaseModel):
    provider: ModelProvider
    model_name: str
    base_url: str
    api_key: SecretStr
    name: str = "default"
    is_default: bool = True
    description: str = ""
    timeout_seconds: int = 30
    temperature: float = 0.2
    max_tokens: int = 1024
    prompt_cache_enabled: bool = True
    prompt_cache_ttl: Literal["ephemeral", "one_hour"] = "ephemeral"
    provider_options: dict[str, Any] = Field(default_factory=dict)


class TerminalContextAttachment(BaseModel):
    terminal_id: str
    selection_label: str
    selected_text: str
