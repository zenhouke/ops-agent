import { useCallback, useRef, useState } from 'react'
import {
  createKnowledgeEntry,
  deleteKnowledgeEntry,
  generateKnowledgeDraft,
  reindexKnowledgeEntries,
  searchKnowledgeEntries,
  updateKnowledgeEntry,
} from '../api/knowledge'
import type {
  KnowledgeDraft,
  KnowledgeEntry,
  KnowledgeEntryPayload,
  KnowledgeGenerateDraftResponse,
  KnowledgeReindexResponse,
  KnowledgeSearchParams,
  KnowledgeSearchResponse,
  KnowledgeSourceConversation,
} from '../types/ops'

const DEFAULT_SEARCH_RESPONSE: KnowledgeSearchResponse = {
  items: [],
  total: 0,
  limit: 0,
  offset: 0,
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function buildPayloadFromDraft(
  draft: KnowledgeDraft,
  sourceConversation: KnowledgeSourceConversation | null,
  overrides: Partial<KnowledgeEntryPayload> = {},
): KnowledgeEntryPayload {
  return {
    ...draft,
    sourceConversationId: sourceConversation?.id ?? null,
    sourceConversationTitle: sourceConversation?.title ?? '',
    sourceConversationUpdatedAt: sourceConversation?.updatedAt ?? null,
    ...overrides,
  }
}

export function useKnowledgeBase() {
  const [entries, setEntries] = useState<KnowledgeEntry[]>([])
  const [total, setTotal] = useState(0)
  const [limit, setLimit] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraftState] = useState<KnowledgeDraft | null>(null)
  const [draftSourceConversation, setDraftSourceConversation] = useState<KnowledgeSourceConversation | null>(null)
  const [draftLoading, setDraftLoading] = useState(false)
  const [draftError, setDraftError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [reindexing, setReindexing] = useState(false)

  const lastSearchParamsRef = useRef<KnowledgeSearchParams | undefined>(undefined)
  const searchRequestRef = useRef(0)
  const draftRequestRef = useRef(0)

  const applySearchResponse = useCallback((response: KnowledgeSearchResponse) => {
    setEntries(response.items)
    setTotal(response.total)
    setLimit(response.limit)
    setOffset(response.offset)
  }, [])

  const search = useCallback(async (params?: KnowledgeSearchParams): Promise<KnowledgeSearchResponse> => {
    const requestId = searchRequestRef.current + 1
    searchRequestRef.current = requestId
    lastSearchParamsRef.current = params
    setLoading(true)
    setError(null)

    try {
      const response = await searchKnowledgeEntries(params)
      if (searchRequestRef.current === requestId) {
        applySearchResponse(response)
      }
      return response
    } catch (searchError) {
      const fallbackResponse = {
        ...DEFAULT_SEARCH_RESPONSE,
        limit: params?.limit ?? 0,
        offset: params?.offset ?? 0,
      }
      if (searchRequestRef.current === requestId) {
        setError(getErrorMessage(searchError, 'Failed to search knowledge entries'))
        applySearchResponse(fallbackResponse)
      }
      return fallbackResponse
    } finally {
      if (searchRequestRef.current === requestId) {
        setLoading(false)
      }
    }
  }, [applySearchResponse])

  const refreshCurrentSearch = useCallback(async () => {
    return search(lastSearchParamsRef.current)
  }, [search])

  const generateDraft = useCallback(async (
    conversationId: string,
    payload: { maxSourceEvents?: number; modelName?: string | null } = {},
  ): Promise<KnowledgeGenerateDraftResponse | null> => {
    const requestId = draftRequestRef.current + 1
    draftRequestRef.current = requestId
    setDraftLoading(true)
    setDraftError(null)

    try {
      const response = await generateKnowledgeDraft(conversationId, payload)
      if (draftRequestRef.current === requestId) {
        setDraftState(response.draft)
        setDraftSourceConversation(response.sourceConversation)
      }
      return response
    } catch (generateError) {
      if (draftRequestRef.current === requestId) {
        setDraftError(getErrorMessage(generateError, 'Failed to generate knowledge draft'))
        setDraftState(null)
        setDraftSourceConversation(null)
      }
      return null
    } finally {
      if (draftRequestRef.current === requestId) {
        setDraftLoading(false)
      }
    }
  }, [])

  const clearDraft = useCallback(() => {
    draftRequestRef.current += 1
    setDraftState(null)
    setDraftSourceConversation(null)
    setDraftError(null)
    setDraftLoading(false)
  }, [])

  const setDraft = useCallback((nextDraft: KnowledgeDraft | null) => {
    setDraftState(nextDraft)
  }, [])

  const saveDraft = useCallback(async (payload: Partial<KnowledgeEntryPayload> = {}): Promise<KnowledgeEntry | null> => {
    if (!draft) {
      setDraftError('No knowledge draft to save')
      return null
    }

    setSaving(true)
    setError(null)
    setDraftError(null)

    try {
      const entry = await createKnowledgeEntry(buildPayloadFromDraft(draft, draftSourceConversation, payload))
      setDraftState(null)
      setDraftSourceConversation(null)
      await refreshCurrentSearch()
      return entry
    } catch (saveError) {
      const message = getErrorMessage(saveError, 'Failed to save knowledge draft')
      setError(message)
      setDraftError(message)
      return null
    } finally {
      setSaving(false)
    }
  }, [draft, draftSourceConversation, refreshCurrentSearch])

  const updateEntry = useCallback(async (entryId: string, payload: KnowledgeEntryPayload): Promise<KnowledgeEntry | null> => {
    setSaving(true)
    setError(null)

    try {
      const entry = await updateKnowledgeEntry(entryId, payload)
      await refreshCurrentSearch()
      return entry
    } catch (updateError) {
      setError(getErrorMessage(updateError, 'Failed to update knowledge entry'))
      return null
    } finally {
      setSaving(false)
    }
  }, [refreshCurrentSearch])

  const deleteEntry = useCallback(async (entryId: string): Promise<boolean> => {
    setError(null)

    try {
      await deleteKnowledgeEntry(entryId)
      await refreshCurrentSearch()
      return true
    } catch (deleteError) {
      setError(getErrorMessage(deleteError, 'Failed to delete knowledge entry'))
      return false
    }
  }, [refreshCurrentSearch])

  const reindex = useCallback(async (): Promise<KnowledgeReindexResponse | null> => {
    setReindexing(true)
    setError(null)

    try {
      const response = await reindexKnowledgeEntries()
      await refreshCurrentSearch()
      return response
    } catch (reindexError) {
      setError(getErrorMessage(reindexError, 'Failed to reindex knowledge entries'))
      return null
    } finally {
      setReindexing(false)
    }
  }, [refreshCurrentSearch])

  return {
    entries,
    total,
    limit,
    offset,
    loading,
    error,
    draft,
    draftSourceConversation,
    draftLoading,
    draftError,
    saving,
    reindexing,
    search,
    generateDraft,
    clearDraft,
    saveDraft,
    updateEntry,
    deleteEntry,
    reindex,
    setDraft,
  }
}

export type KnowledgeBaseController = ReturnType<typeof useKnowledgeBase>
