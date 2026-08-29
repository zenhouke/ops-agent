import { requestJson, requestVoid } from './client'
import { mapRequiredTimestamps } from './mappers'
import type { ConversationAppendEventsResponseDto, ConversationContextStatusDto, ConversationCreateResponseDto, ConversationDetailDto, ConversationEventsPageDto, ConversationSummaryDto } from '../types/api'
import type { ConversationContextStatus, ConversationDetail, ConversationEventsPage, ConversationSummary, EventItem } from '../types/ops'

export function mapConversationSummary(dto: ConversationSummaryDto): ConversationSummary {
  return {
    id: dto.id,
    title: dto.title,
    selectedModel: dto.selected_model,
    ...mapRequiredTimestamps(dto),
    eventCount: dto.event_count,
    lastEventKind: dto.last_event_kind,
    assetId: dto.asset_id,
    scopeMode: dto.scope_mode,
    allowedAssetIds: dto.allowed_asset_ids,
  }
}

export function mapConversationDetail(dto: ConversationDetailDto): ConversationDetail {
  return {
    id: dto.id,
    title: dto.title,
    selectedModel: dto.selected_model,
    ...mapRequiredTimestamps(dto),
    events: dto.events,
    assetId: dto.asset_id,
    scopeMode: dto.scope_mode,
    allowedAssetIds: dto.allowed_asset_ids,
  }
}

export function mapConversationEventsPage(dto: ConversationEventsPageDto): ConversationEventsPage {
  return {
    conversation: mapConversationSummary(dto.conversation),
    events: dto.events,
    offset: dto.offset,
    limit: dto.limit,
    total: dto.total,
    hasMoreBefore: dto.has_more_before,
    hasMoreAfter: dto.has_more_after,
  }
}

export function mapConversationAppendResponse(dto: ConversationAppendEventsResponseDto): { conversation: ConversationSummary; appendedCount: number } {
  return {
    conversation: mapConversationSummary(dto.conversation),
    appendedCount: dto.appended_count,
  }
}

export function mapConversationContextStatus(dto: ConversationContextStatusDto): ConversationContextStatus {
  return {
    contextPercent: dto.context_percent,
    contextStatus: dto.context_status,
    tokenUsage: dto.token_usage
      ? {
          inputTokens: dto.token_usage.input_tokens,
          outputTokens: dto.token_usage.output_tokens,
          cacheCreationInputTokens: dto.token_usage.cache_creation_input_tokens,
          cacheReadInputTokens: dto.token_usage.cache_read_input_tokens,
          totalTokens: dto.token_usage.total_tokens,
          measurement: dto.token_usage.measurement,
        }
      : undefined,
  }
}

export async function getConversations(): Promise<ConversationSummary[]> {
  const conversations = await requestJson<ConversationSummaryDto[]>('/api/conversations')
  return conversations.map(mapConversationSummary)
}

export async function createConversation(
  selectedModel: string | null,
  assetId: number,
  scopeMode: 'single' | 'multi' = 'single',
): Promise<{ conversation: ConversationSummary; events: EventItem[] }> {
  const response = await requestJson<ConversationCreateResponseDto>('/api/conversations', {
    method: 'POST',
    body: JSON.stringify({ selected_model: selectedModel, asset_id: assetId, scope_mode: scopeMode }),
  })
  return {
    conversation: mapConversationSummary(response.conversation),
    events: response.events,
  }
}

export async function rewriteConversation(
  conversationId: string,
  beforeEventId: string,
): Promise<{ conversation: ConversationSummary; events: EventItem[] }> {
  const response = await requestJson<ConversationCreateResponseDto>(`/api/conversations/${conversationId}/rewrite`, {
    method: 'POST',
    body: JSON.stringify({ before_event_id: beforeEventId }),
  })
  return {
    conversation: mapConversationSummary(response.conversation),
    events: response.events,
  }
}

export async function getConversation(conversationId: string): Promise<ConversationDetail> {
  const conversation = await requestJson<ConversationDetailDto>(`/api/conversations/${conversationId}`)
  return mapConversationDetail(conversation)
}

export async function getConversationEventsTail(conversationId: string, limit = 200): Promise<ConversationEventsPage> {
  const page = await requestJson<ConversationEventsPageDto>(`/api/conversations/${conversationId}/events?tail=${limit}`)
  return mapConversationEventsPage(page)
}

export async function getConversationEventsPage(conversationId: string, offset: number, limit = 200): Promise<ConversationEventsPage> {
  const page = await requestJson<ConversationEventsPageDto>(`/api/conversations/${conversationId}/events?offset=${offset}&limit=${limit}`)
  return mapConversationEventsPage(page)
}

export async function getConversationContext(conversationId: string): Promise<ConversationContextStatus> {
  const status = await requestJson<ConversationContextStatusDto>(`/api/conversations/${conversationId}/context`)
  return mapConversationContextStatus(status)
}

export async function appendConversationEvents(conversationId: string, events: EventItem[]): Promise<{ conversation: ConversationSummary; appendedCount: number }> {
  const response = await requestJson<ConversationAppendEventsResponseDto>(`/api/conversations/${conversationId}/events`, {
    method: 'POST',
    body: JSON.stringify({ events }),
  })
  return mapConversationAppendResponse(response)
}

export async function deleteConversation(conversationId: string, cancelActive = false): Promise<void> {
  const query = cancelActive ? '?cancel_active=true' : ''
  await requestVoid(`/api/conversations/${conversationId}${query}`, {
    method: 'DELETE',
  })
}
