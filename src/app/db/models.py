from datetime import UTC, datetime
from typing import ClassVar

from sqlmodel import Field, SQLModel


class AssetGroup(SQLModel, table=True):
    __tablename__: ClassVar[str] = "asset_groups"  # pyright: ignore[reportIncompatibleVariableOverride]
    id: int | None = Field(default=None, primary_key=True)
    name: str
    description: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Asset(SQLModel, table=True):
    __tablename__: ClassVar[str] = "assets"  # pyright: ignore[reportIncompatibleVariableOverride]
    id: int | None = Field(default=None, primary_key=True)
    group_id: int | None = None
    ssh_key_id: int | None = None
    proxy_asset_id: int | None = None
    name: str
    asset_type: str
    host: str = ""
    port: int = 22
    username: str = ""
    auth_type: str = ""
    tags: str = ""
    vendor: str = ""
    description: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Credential(SQLModel, table=True):
    __tablename__: ClassVar[str] = "credentials"  # pyright: ignore[reportIncompatibleVariableOverride]
    id: int | None = Field(default=None, primary_key=True)
    asset_id: int
    encryption_version: str
    encrypted_blob: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SSHKey(SQLModel, table=True):
    __tablename__: ClassVar[str] = "ssh_keys"  # pyright: ignore[reportIncompatibleVariableOverride]
    id: int | None = Field(default=None, primary_key=True)
    name: str
    public_key: str = ""
    private_key_encryption_version: str
    encrypted_private_key: str
    passphrase_encryption_version: str | None = None
    encrypted_passphrase: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ModelConfigRecord(SQLModel, table=True):
    __tablename__: ClassVar[str] = "model_configs"  # pyright: ignore[reportIncompatibleVariableOverride]
    id: int | None = Field(default=None, primary_key=True)
    name: str
    provider: str
    base_url: str
    api_key_encryption_version: str
    encrypted_api_key: str
    model_name: str
    is_default: bool = False
    timeout_seconds: int = 30
    temperature: float = 0.2
    max_tokens: int = 1024
    description: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))



class ModelUsage(SQLModel, table=True):
    __tablename__: ClassVar[str] = "model_usages"  # pyright: ignore[reportIncompatibleVariableOverride]
    id: int | None = Field(default=None, primary_key=True)
    task_id: int | None = None
    runtime_id: str = ""
    conversation_id: str = ""
    model_config_id: int | None = None
    provider: str
    model_name: str
    base_url_snapshot: str
    temperature_snapshot: float
    max_tokens_snapshot: int
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    total_tokens: int = 0
    call_kind: str = "agent"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuditLog(SQLModel, table=True):
    __tablename__: ClassVar[str] = "audit_logs"  # pyright: ignore[reportIncompatibleVariableOverride]
    id: int | None = Field(default=None, primary_key=True)
    action: str
    entity_type: str
    actor: str = ""
    entity_id: int | None = None
    asset_id: int | None = None
    conversation_id: str | None = None
    task_id: int | None = None
    details: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ScheduledJob(SQLModel, table=True):
    __tablename__: ClassVar[str] = "scheduled_jobs"  # pyright: ignore[reportIncompatibleVariableOverride]
    id: int | None = Field(default=None, primary_key=True)
    name: str
    asset_id: int
    prompt: str
    interval_seconds: int = 3600
    enabled: bool = True
    last_run_at: datetime | None = None
    run_status: str = "idle"
    lease_owner: str = ""
    lease_expires_at: datetime | None = None
    last_finished_at: datetime | None = None
    last_error: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Alert(SQLModel, table=True):
    __tablename__: ClassVar[str] = "alerts"  # pyright: ignore[reportIncompatibleVariableOverride]
    id: int | None = Field(default=None, primary_key=True)
    job_id: int | None = None
    asset_id: int
    runtime_id: str | None = None
    conversation_id: str | None = None
    severity: str = "warning"  # 'info', 'warning', 'critical'
    title: str
    message: str
    status: str = "unread"  # 'unread', 'resolved', 'ignored'
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
