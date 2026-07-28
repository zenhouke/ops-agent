from pydantic import BaseModel, Field


class KnowledgeCommandView(BaseModel):
    command: str = ""
    purpose: str = ""
    outcome: str = ""


class KnowledgeAssetRefView(BaseModel):
    assetId: int | None = None
    label: str = ""


class KnowledgeSourceRefView(BaseModel):
    conversationId: str | None = None
    eventId: str | None = None
    eventIndex: int | None = None
    eventType: str = ""
    quote: str = ""
    relevance: str = ""


class KnowledgeSourceConversationView(BaseModel):
    id: str | None = None
    title: str = ""
    updatedAt: str | None = None


class KnowledgeDraftView(BaseModel):
    title: str = ""
    summary: str = ""
    problem: str = ""
    diagnosis: str = ""
    resolution: str = ""
    commands: list[KnowledgeCommandView] = Field(default_factory=list)
    assets: list[KnowledgeAssetRefView] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    sources: list[KnowledgeSourceRefView] = Field(default_factory=list)
    redactionWarnings: list[str] = Field(default_factory=list)


class KnowledgeGenerateDraftRequest(BaseModel):
    maxSourceEvents: int = 120
    modelName: str | None = None


class KnowledgeGenerateDraftResponse(BaseModel):
    draft: KnowledgeDraftView
    sourceConversation: KnowledgeSourceConversationView


class KnowledgeEntryCreateRequest(BaseModel):
    title: str = ""
    summary: str = ""
    problem: str = ""
    diagnosis: str = ""
    resolution: str = ""
    commands: list[KnowledgeCommandView] = Field(default_factory=list)
    assets: list[KnowledgeAssetRefView] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    sources: list[KnowledgeSourceRefView] = Field(default_factory=list)
    redactionWarnings: list[str] = Field(default_factory=list)
    sourceConversationId: str | None = None
    sourceConversationTitle: str = ""
    sourceConversationUpdatedAt: str | None = None


class KnowledgeEntryUpdateRequest(BaseModel):
    title: str = ""
    summary: str = ""
    problem: str = ""
    diagnosis: str = ""
    resolution: str = ""
    commands: list[KnowledgeCommandView] = Field(default_factory=list)
    assets: list[KnowledgeAssetRefView] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    sources: list[KnowledgeSourceRefView] = Field(default_factory=list)
    redactionWarnings: list[str] = Field(default_factory=list)
    sourceConversationId: str | None = None
    sourceConversationTitle: str = ""
    sourceConversationUpdatedAt: str | None = None


class KnowledgeEntryView(BaseModel):
    id: str
    title: str
    summary: str = ""
    problem: str = ""
    diagnosis: str = ""
    resolution: str = ""
    commands: list[KnowledgeCommandView] = Field(default_factory=list)
    assets: list[KnowledgeAssetRefView] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    sources: list[KnowledgeSourceRefView] = Field(default_factory=list)
    sourceConversation: KnowledgeSourceConversationView = Field(default_factory=KnowledgeSourceConversationView)
    createdAt: str
    updatedAt: str


class KnowledgeSearchResponse(BaseModel):
    items: list[KnowledgeEntryView] = Field(default_factory=list)
    total: int = 0
    limit: int = 20
    offset: int = 0


class KnowledgeReindexResponse(BaseModel):
    indexed: int = 0
    failed: int = 0
