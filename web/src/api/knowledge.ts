import { requestJson, requestVoid } from './client'
import type {
  KnowledgeDraftDto,
  KnowledgeEntryDto,
  KnowledgeEntryPayloadDto,
  KnowledgeGenerateDraftRequestDto,
  KnowledgeGenerateDraftResponseDto,
  KnowledgeReindexResponseDto,
  KnowledgeSearchResponseDto,
} from '../types/api'
import type {
  KnowledgeAssetRef,
  KnowledgeCommand,
  KnowledgeDraft,
  KnowledgeEntry,
  KnowledgeEntryPayload,
  KnowledgeGenerateDraftResponse,
  KnowledgeReindexResponse,
  KnowledgeSearchParams,
  KnowledgeSearchResponse,
  KnowledgeSourceConversation,
  KnowledgeSourceRef,
} from '../types/ops'

export function mapKnowledgeCommand(dto: KnowledgeCommand): KnowledgeCommand {
  return {
    command: dto.command,
    purpose: dto.purpose,
    outcome: dto.outcome,
  }
}

export function mapKnowledgeAssetRef(dto: KnowledgeAssetRef): KnowledgeAssetRef {
  return {
    assetId: dto.assetId,
    label: dto.label,
  }
}

export function mapKnowledgeSourceRef(dto: KnowledgeSourceRef): KnowledgeSourceRef {
  return {
    conversationId: dto.conversationId,
    eventId: dto.eventId,
    eventIndex: dto.eventIndex,
    eventType: dto.eventType,
    quote: dto.quote,
    relevance: dto.relevance,
  }
}

export function mapKnowledgeSourceConversation(dto: KnowledgeSourceConversation): KnowledgeSourceConversation {
  return {
    id: dto.id,
    title: dto.title,
    updatedAt: dto.updatedAt,
  }
}

export function mapKnowledgeDraft(dto: KnowledgeDraftDto): KnowledgeDraft {
  return {
    title: dto.title,
    summary: dto.summary,
    problem: dto.problem,
    diagnosis: dto.diagnosis,
    resolution: dto.resolution,
    commands: dto.commands.map(mapKnowledgeCommand),
    assets: dto.assets.map(mapKnowledgeAssetRef),
    tags: [...dto.tags],
    sources: dto.sources.map(mapKnowledgeSourceRef),
    redactionWarnings: [...dto.redactionWarnings],
  }
}

export function mapKnowledgeEntry(dto: KnowledgeEntryDto): KnowledgeEntry {
  return {
    id: dto.id,
    title: dto.title,
    summary: dto.summary,
    problem: dto.problem,
    diagnosis: dto.diagnosis,
    resolution: dto.resolution,
    commands: dto.commands.map(mapKnowledgeCommand),
    assets: dto.assets.map(mapKnowledgeAssetRef),
    tags: [...dto.tags],
    sources: dto.sources.map(mapKnowledgeSourceRef),
    sourceConversation: mapKnowledgeSourceConversation(dto.sourceConversation),
    createdAt: dto.createdAt,
    updatedAt: dto.updatedAt,
  }
}

export function mapKnowledgeGenerateDraftResponse(dto: KnowledgeGenerateDraftResponseDto): KnowledgeGenerateDraftResponse {
  return {
    draft: mapKnowledgeDraft(dto.draft),
    sourceConversation: mapKnowledgeSourceConversation(dto.sourceConversation),
  }
}

export function mapKnowledgeSearchResponse(dto: KnowledgeSearchResponseDto): KnowledgeSearchResponse {
  return {
    items: dto.items.map(mapKnowledgeEntry),
    total: dto.total,
    limit: dto.limit,
    offset: dto.offset,
  }
}

export function mapKnowledgeReindexResponse(dto: KnowledgeReindexResponseDto): KnowledgeReindexResponse {
  return {
    indexed: dto.indexed,
    failed: dto.failed,
  }
}

function buildKnowledgeSearchQuery(params?: KnowledgeSearchParams): string {
  if (!params) {
    return ''
  }

  const query = new URLSearchParams()
  const appendString = (key: string, value: string | undefined) => {
    if (value !== undefined && value.trim() !== '') {
      query.set(key, value)
    }
  }
  const appendNumber = (key: string, value: number | undefined) => {
    if (value !== undefined) {
      query.set(key, String(value))
    }
  }

  appendString('query', params.query)
  appendNumber('assetId', params.assetId)
  appendString('tag', params.tag)
  appendString('sourceConversationId', params.sourceConversationId)
  appendNumber('limit', params.limit)
  appendNumber('offset', params.offset)

  const serialized = query.toString()
  return serialized ? `?${serialized}` : ''
}

function toKnowledgeEntryPayloadDto(payload: KnowledgeEntryPayload): KnowledgeEntryPayloadDto {
  return {
    title: payload.title,
    summary: payload.summary,
    problem: payload.problem,
    diagnosis: payload.diagnosis,
    resolution: payload.resolution,
    commands: payload.commands.map(mapKnowledgeCommand),
    assets: payload.assets.map(mapKnowledgeAssetRef),
    tags: [...payload.tags],
    sources: payload.sources.map(mapKnowledgeSourceRef),
    redactionWarnings: [...payload.redactionWarnings],
    sourceConversationId: payload.sourceConversationId,
    sourceConversationTitle: payload.sourceConversationTitle,
    sourceConversationUpdatedAt: payload.sourceConversationUpdatedAt,
  }
}

export async function generateKnowledgeDraft(
  conversationId: string,
  payload: KnowledgeGenerateDraftRequestDto = {},
): Promise<KnowledgeGenerateDraftResponse> {
  const response = await requestJson<KnowledgeGenerateDraftResponseDto>(`/api/knowledge/from-conversation/${conversationId}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return mapKnowledgeGenerateDraftResponse(response)
}

export async function createKnowledgeEntry(payload: KnowledgeEntryPayload): Promise<KnowledgeEntry> {
  const entry = await requestJson<KnowledgeEntryDto>('/api/knowledge', {
    method: 'POST',
    body: JSON.stringify(toKnowledgeEntryPayloadDto(payload)),
  })
  return mapKnowledgeEntry(entry)
}

export async function searchKnowledgeEntries(params?: KnowledgeSearchParams): Promise<KnowledgeSearchResponse> {
  const response = await requestJson<KnowledgeSearchResponseDto>(`/api/knowledge${buildKnowledgeSearchQuery(params)}`)
  return mapKnowledgeSearchResponse(response)
}

export async function getKnowledgeEntry(entryId: string): Promise<KnowledgeEntry> {
  const entry = await requestJson<KnowledgeEntryDto>(`/api/knowledge/${entryId}`)
  return mapKnowledgeEntry(entry)
}

export async function updateKnowledgeEntry(entryId: string, payload: KnowledgeEntryPayload): Promise<KnowledgeEntry> {
  const entry = await requestJson<KnowledgeEntryDto>(`/api/knowledge/${entryId}`, {
    method: 'PUT',
    body: JSON.stringify(toKnowledgeEntryPayloadDto(payload)),
  })
  return mapKnowledgeEntry(entry)
}

export async function deleteKnowledgeEntry(entryId: string): Promise<void> {
  await requestVoid(`/api/knowledge/${entryId}`, {
    method: 'DELETE',
  })
}

export async function reindexKnowledgeEntries(): Promise<KnowledgeReindexResponse> {
  const response = await requestJson<KnowledgeReindexResponseDto>('/api/knowledge/reindex', {
    method: 'POST',
  })
  return mapKnowledgeReindexResponse(response)
}

export type KnowledgeExtractionJob = {
  id: string
  conversation_id: string
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  created_ids: string[]
  updated_ids: string[]
  kept_ids: string[]
  error: string | null
  total_batches: number
  completed_batches: number
  retry_count: number
  progress: string
}

export async function startKnowledgeExtraction(conversationId: string, modelName: string | null): Promise<KnowledgeExtractionJob> {
  return requestJson(`/api/knowledge/extractions/${encodeURIComponent(conversationId)}`, {
    method: 'POST', body: JSON.stringify({ modelName }),
  })
}

export async function getKnowledgeExtraction(conversationId: string): Promise<{ job: KnowledgeExtractionJob | null; entries: KnowledgeEntry[] }> {
  const response = await requestJson<{ job: KnowledgeExtractionJob | null; entries: KnowledgeEntryDto[] }>(`/api/knowledge/extractions/${encodeURIComponent(conversationId)}`)
  return { job: response.job, entries: response.entries.map(mapKnowledgeEntry) }
}

export async function getKnowledgeMarkdown(entryId: string): Promise<string> {
  const response = await requestJson<{ markdown: string }>(`/api/knowledge/${encodeURIComponent(entryId)}/markdown`)
  return response.markdown
}

export type KnowledgeVersion = { id: string; updatedAt: string; title: string }
export type KnowledgeVersionPreview = { markdown: string; diff: string; currentUpdatedAt: string }

export function getKnowledgeVersions(entryId: string): Promise<KnowledgeVersion[]> {
  return requestJson(`/api/knowledge/${encodeURIComponent(entryId)}/versions`)
}

export function getKnowledgeVersion(entryId: string, versionId: string): Promise<KnowledgeVersionPreview> {
  return requestJson(`/api/knowledge/${encodeURIComponent(entryId)}/versions/${encodeURIComponent(versionId)}`)
}

export async function restoreKnowledgeVersion(entryId: string, versionId: string, expectedUpdatedAt: string): Promise<KnowledgeEntry> {
  const response = await requestJson<KnowledgeEntryDto>(`/api/knowledge/${encodeURIComponent(entryId)}/versions/${encodeURIComponent(versionId)}/restore`, {
    method: 'POST', body: JSON.stringify({ expectedUpdatedAt }),
  })
  return mapKnowledgeEntry(response)
}
