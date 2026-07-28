export type KnowledgeCommand = {
  command: string
  purpose: string
  outcome: string
}

export type KnowledgeAssetRef = {
  assetId: number | null
  label: string
}

export type KnowledgeSourceRef = {
  conversationId: string | null
  eventId: string | null
  eventIndex: number | null
  eventType: string
  quote: string
  relevance: string
}

export type KnowledgeSourceConversation = {
  id: string | null
  title: string
  updatedAt: string | null
}

export type KnowledgeDraft = {
  title: string
  summary: string
  problem: string
  diagnosis: string
  resolution: string
  commands: KnowledgeCommand[]
  assets: KnowledgeAssetRef[]
  tags: string[]
  sources: KnowledgeSourceRef[]
  redactionWarnings: string[]
}

export type KnowledgeEntry = Omit<KnowledgeDraft, 'redactionWarnings'> & {
  id: string
  sourceConversation: KnowledgeSourceConversation
  createdAt: string
  updatedAt: string
}

export type KnowledgeSearchResponse = {
  items: KnowledgeEntry[]
  total: number
  limit: number
  offset: number
}

export type KnowledgeReindexResponse = {
  indexed: number
  failed: number
}

export type KnowledgeGenerateDraftResponse = {
  draft: KnowledgeDraft
  sourceConversation: KnowledgeSourceConversation
}

export type KnowledgeEntryPayload = KnowledgeDraft & {
  sourceConversationId?: string | null
  sourceConversationTitle?: string
  sourceConversationUpdatedAt?: string | null
}

export type KnowledgeSearchParams = {
  query?: string
  assetId?: number
  tag?: string
  sourceConversationId?: string
  limit?: number
  offset?: number
}

