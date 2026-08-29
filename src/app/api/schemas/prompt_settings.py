from pydantic import BaseModel, ConfigDict, Field


def _to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class PromptOverrides(BaseModel):
    agent_behavior: str = ""
    incident_response: str = ""
    knowledge_extraction: str = ""
    memory_usage: str = ""
    organization_rules: str = ""

    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True, extra="forbid")


class PromptSettingsUpdateRequest(BaseModel):
    revision: int = Field(ge=0)
    overrides: PromptOverrides


class PromptSettingsResetRequest(BaseModel):
    revision: int = Field(ge=0)


class PromptSettingsView(BaseModel):
    schema_version: int
    revision: int
    overrides: PromptOverrides
    defaults: PromptOverrides
    effective: PromptOverrides
    updated_at: str | None
    immutable_safety_summary: str
    max_prompt_chars: int

    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)
