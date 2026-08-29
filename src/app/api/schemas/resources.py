from typing import Any, Literal

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.shared.schemas import AssetCreate


class AssetGroupCreate(BaseModel):
    name: str
    description: str = ""


class AssetGroupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class AssetGroupView(BaseModel):
    id: int
    name: str
    description: str
    created_at: datetime
    updated_at: datetime


class AssetView(BaseModel):
    id: int
    group_id: int | None = None
    ssh_key_id: int | None = None
    proxy_asset_id: int | None = None
    name: str
    asset_type: str
    host: str
    port: int
    username: str
    auth_type: str
    tags: list[str]
    vendor: str
    description: str


class AssetConnectionTestRequest(BaseModel):
    asset_id: int | None = None
    asset: AssetCreate


class AssetConnectionTestView(BaseModel):
    success: bool
    message: str
    detected_device_type: str | None = None
    detected_asset_type: str | None = None
    prompt: str | None = None


class TerminalEventSummaryView(BaseModel):
    id: int
    event_type: str
    event_data: str
    created_at: datetime


class AssetContextView(BaseModel):
    asset: AssetView
    recent_terminal_events: list[TerminalEventSummaryView]


class ModelsView(BaseModel):
    provider: str
    selected_model: str
    available_models: list[str]


class ModelConfigView(BaseModel):
    id: int
    name: str
    provider: str
    base_url: str
    api_key_masked: str
    model_name: str
    is_default: bool
    timeout_seconds: int = 30
    temperature: float = 0.2
    max_tokens: int = 1024
    prompt_cache_enabled: bool = True
    prompt_cache_ttl: Literal["ephemeral", "one_hour"] = "ephemeral"
    description: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ModelConfigCreate(BaseModel):
    name: str
    provider: str
    base_url: str
    api_key: SecretStr
    model_name: str = Field(min_length=1)
    is_default: bool = False
    timeout_seconds: int = 30
    temperature: float = 0.2
    max_tokens: int = 1024
    prompt_cache_enabled: bool = True
    prompt_cache_ttl: Literal["ephemeral", "one_hour"] = "ephemeral"
    description: str = ""


class ModelConfigUpdate(BaseModel):
    name: str | None = None
    provider: str | None = None
    base_url: str | None = None
    api_key: SecretStr | None = None
    model_name: str | None = Field(default=None, min_length=1)
    is_default: bool | None = None
    timeout_seconds: int | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    prompt_cache_enabled: bool | None = None
    prompt_cache_ttl: Literal["ephemeral", "one_hour"] | None = None
    description: str | None = None


class ModelConnectionTestRequest(BaseModel):
    provider: str
    base_url: str
    api_key: SecretStr
    model_name: str = Field(min_length=1)
    timeout_seconds: int = 30
    temperature: float = 0.2
    max_tokens: int = 1024
    prompt_cache_enabled: bool = True
    prompt_cache_ttl: Literal["ephemeral", "one_hour"] = "ephemeral"
    provider_options: dict[str, Any] = Field(default_factory=dict)


class ModelConnectionTestResponse(BaseModel):
    success: bool
    message: str


class ModelDiscoveryRequest(BaseModel):
    provider: str
    base_url: str
    api_key: SecretStr
    timeout_seconds: int = 30
    provider_options: dict[str, Any] = Field(default_factory=dict)


class ModelDiscoveryResponse(BaseModel):
    models: list[str]


class MCPToolView(BaseModel):
    id: str
    original_name: str
    exposed_name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    approval_policy: Literal["allow", "ask", "deny"]
    enabled: bool
    discovered: bool
    last_discovered_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class MCPServerView(BaseModel):
    id: str
    name: str
    slug: str
    enabled: bool
    transport: Literal["stdio", "http_sse"]
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int
    connection_status: Literal["untested", "ok", "failed"]
    discovery_status: Literal["never", "ok", "failed"]
    last_error: str
    last_discovered_at: str | None = None
    last_refresh_succeeded: bool
    tools: list[MCPToolView] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None


class MCPServerCreate(BaseModel):
    name: str
    transport: Literal["stdio", "http_sse"]
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = 30


class MCPServerUpdate(BaseModel):
    name: str | None = None
    transport: Literal["stdio", "http_sse"] | None = None
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    url: str | None = None
    headers: dict[str, str] | None = None
    timeout_seconds: int | None = None


class MCPServerEnableRequest(BaseModel):
    enabled: bool


class MCPToolUpdate(BaseModel):
    enabled: bool | None = None
    approval_policy: Literal["allow", "ask", "deny"] | None = None


class MCPConnectionTestResponse(BaseModel):
    success: bool
    message: str
    server: MCPServerView | None = None


class SSHKeyView(BaseModel):
    id: int
    name: str
    public_key: str
    has_passphrase: bool
    created_at: datetime
    updated_at: datetime

