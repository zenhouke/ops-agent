from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal


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


class KnowledgeExtractionAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["create", "update", "keep"]
    entry_id: str | None = None
    draft: KnowledgeDraft | None = None


class KnowledgeExtractionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actions: list[KnowledgeExtractionAction] = Field(max_length=20)


class KnowledgeExtractionJob(BaseModel):
    id: str
    conversation_id: str
    status: Literal["queued", "running", "succeeded", "failed"] = "queued"
    created_at: str
    updated_at: str
    created_ids: list[str] = Field(default_factory=list)
    updated_ids: list[str] = Field(default_factory=list)
    kept_ids: list[str] = Field(default_factory=list)
    error: str | None = None
    total_batches: int = 0
    completed_batches: int = 0
    retry_count: int = 0
    progress: str = ""


class KnowledgeExtractionBatch(BaseModel):
    key: str
    document: str
    fingerprints: list[str]


class KnowledgeExtractionTask(KnowledgeExtractionJob):
    source: KnowledgeSourceConversation = Field(default_factory=KnowledgeSourceConversation)
    model_name: str | None = None
    batches: list[KnowledgeExtractionBatch] = Field(default_factory=list)


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
