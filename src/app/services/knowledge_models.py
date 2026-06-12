from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeCommand(BaseModel):
    command: str = ""
    purpose: str = ""
    outcome: str = ""


class KnowledgeAssetRef(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    asset_id: int | None = Field(default=None, alias="assetId")
    label: str = ""


class KnowledgeSourceRef(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    conversation_id: str | None = Field(default=None, alias="conversationId")
    event_id: str | None = Field(default=None, alias="eventId")
    event_index: int | None = Field(default=None, alias="eventIndex")
    event_type: str = Field(default="", alias="eventType")
    quote: str = ""
    relevance: str = ""


class KnowledgeSourceConversation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    title: str = ""
    updated_at: str | None = Field(default=None, alias="updatedAt")


class KnowledgeEntry(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    title: str
    summary: str = ""
    problem: str = ""
    diagnosis: str = ""
    resolution: str = ""
    commands: list[KnowledgeCommand] = Field(default_factory=list)
    assets: list[KnowledgeAssetRef] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    sources: list[KnowledgeSourceRef] = Field(default_factory=list)
    source_conversation: KnowledgeSourceConversation = Field(
        default_factory=KnowledgeSourceConversation,
        alias="sourceConversation",
    )
    embedding: list[float] | None = Field(default=None)
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")


class KnowledgeDraft(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str = ""
    summary: str = ""
    problem: str = ""
    diagnosis: str = ""
    resolution: str = ""
    commands: list[KnowledgeCommand] = Field(default_factory=list)
    assets: list[KnowledgeAssetRef] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    sources: list[KnowledgeSourceRef] = Field(default_factory=list)
    redaction_warnings: list[str] = Field(
        default_factory=list,
        alias="redactionWarnings",
    )


class KnowledgeSearchFilters(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    query: str = ""
    asset_id: int | None = Field(default=None, alias="assetId")
    tag: str = ""
    source_conversation_id: str | None = Field(default=None, alias="sourceConversationId")
    limit: int = 20
    offset: int = 0


class KnowledgeSearchHit(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    entry_id: str = Field(alias="entryId")
    score: float = 0.0


class KnowledgeSearchPage(BaseModel):
    items: list[KnowledgeEntry] = Field(default_factory=list)
    total: int = 0
    limit: int = 20
    offset: int = 0


class KnowledgeReindexResult(BaseModel):
    indexed: int = 0
    failed: int = 0
