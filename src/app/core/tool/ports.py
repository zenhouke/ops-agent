"""Narrow inputs and capabilities required by Agent tools; no service or ORM types."""
from dataclasses import dataclass
from typing import Any, Protocol

from app.core.approval import ApprovalContext


@dataclass(frozen=True)
class AssetSummary:
    id: int
    name: str
    asset_type: str
    group_id: int | None = None
    tags: tuple[str, ...] = ()
    host: str = ""
    vendor: str = ""
    group_name: str = ""
    access_via: str = "direct"


class AssetCatalog(Protocol):
    def list_assets(self) -> list[AssetSummary]: ...
    def get_asset(self, asset_id: int) -> AssetSummary | None: ...


class LoadedSkill(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def body(self) -> str: ...


class SkillLoader(Protocol):
    def load_skill(self, name: str) -> LoadedSkill: ...


class CommandPolicy(Protocol):
    def check_command(self, command: str, context: ApprovalContext) -> tuple[str, str]: ...
    def record_submission(self, *, runtime_id: str, terminal_id: str, asset_id: int,
                          conversation_id: str, command: str, approval_policy: str) -> None: ...


@dataclass(frozen=True)
class OpsPluginTool:
    plugin_id: str
    name: str
    exposed_name: str
    description: str
    command_template: str
    input_schema: dict[str, Any]
    asset_types: tuple[str, ...] = ()
