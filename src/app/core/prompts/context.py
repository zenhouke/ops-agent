"""Read-only inputs consumed by prompt formatters, independent of runtime models."""
from typing import Any, Protocol


class PromptTaskState(Protocol):
    def to_payload(self) -> dict[str, Any]: ...


class AgentPromptContext(Protocol):
    @property
    def available_skills(self) -> list[dict[str, str]]: ...

    @property
    def loaded_skill_name(self) -> str | None: ...

    @property
    def manual_skill_content(self) -> str: ...

    @property
    def agent_behavior_prompt(self) -> str: ...

    @property
    def device_context(self) -> str: ...

    @property
    def default_authorization_id(self) -> str | None: ...

    @property
    def task_state(self) -> PromptTaskState: ...

    @property
    def conversation_scope_mode(self) -> str: ...

    @property
    def conversation_primary_asset_id(self) -> int | None: ...

    @property
    def asset_id(self) -> int: ...

    @property
    def allowed_asset_ids(self) -> list[int]: ...

    @property
    def incident_response_prompt(self) -> str: ...

    @property
    def organization_rules_prompt(self) -> str: ...

    @property
    def os_type(self) -> str: ...

    @property
    def asset_summary(self) -> str: ...

    @property
    def shell_type(self) -> str: ...

    @property
    def execution_profile(self) -> str: ...


class DevicePromptContext(Protocol):
    @property
    def vendor(self) -> str: ...

    @property
    def read_prefixes(self) -> tuple[str, ...]: ...

    @property
    def save_commands(self) -> tuple[str, ...]: ...
