import type {
  KnowledgeDraft,
  KnowledgeEntry,
  KnowledgeEntryPayload,
  KnowledgeGenerateDraftResponse,
  KnowledgeReindexResponse,
  KnowledgeSearchParams,
  KnowledgeSearchResponse,
  KnowledgeSourceConversation,
} from '../../types/ops'
import { KnowledgeBrowser } from './KnowledgeBrowser'
import { KnowledgeDraftReview } from './KnowledgeDraftReview'

type KnowledgeDrawerProps = {
  open: boolean
  conversationId: string | null
  selectedModel: string
  draft: KnowledgeDraft | null
  draftSourceConversation: KnowledgeSourceConversation | null
  draftLoading: boolean
  draftError: string | null
  saving: boolean
  entries: KnowledgeEntry[]
  total: number
  limit: number
  offset: number
  loading: boolean
  error: string | null
  reindexing: boolean
  knowledgeEntriesInjected?: number
  knowledgeContextChars?: number
  onClose: () => void
  onSearch: (params?: KnowledgeSearchParams) => Promise<KnowledgeSearchResponse>
  onDeleteEntry: (entryId: string) => Promise<boolean>
  onReindex: () => Promise<KnowledgeReindexResponse | null>
  onGenerateDraft: (conversationId: string, payload?: { maxSourceEvents?: number; modelName?: string | null }) => Promise<KnowledgeGenerateDraftResponse | null>
  onSaveDraft: (payload?: Partial<KnowledgeEntryPayload>) => Promise<KnowledgeEntry | null>
  onClearDraft: () => void
  onDraftChange: (draft: KnowledgeDraft | null) => void
}

export function KnowledgeDrawer({
  open,
  conversationId,
  selectedModel,
  draft,
  draftSourceConversation,
  draftLoading,
  draftError,
  saving,
  entries,
  total,
  limit,
  offset,
  loading,
  error,
  reindexing,
  knowledgeEntriesInjected,
  knowledgeContextChars,
  onClose,
  onSearch,
  onDeleteEntry,
  onReindex,
  onGenerateDraft,
  onSaveDraft,
  onClearDraft,
  onDraftChange,
}: KnowledgeDrawerProps) {
  if (!open) {
    return null
  }

  const hasKnowledgeRuntimeStats = knowledgeEntriesInjected !== undefined || knowledgeContextChars !== undefined

  return (
    <div className="fixed inset-0 z-[70] flex justify-end bg-black/45 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label="全局知识库">
      <button type="button" className="absolute inset-0 cursor-default" aria-label="关闭知识库" onClick={onClose} />
      <aside className="relative flex h-full w-full max-w-[640px] flex-col border-l border-ops-border/20 bg-ops-bg shadow-2xl shadow-black/40 sm:w-[min(640px,92vw)]">
        <header className="flex shrink-0 items-start justify-between gap-4 border-b border-ops-border/15 bg-ops-deep px-5 py-4 dark:bg-ops-panel/90">
          <div className="min-w-0">
            <p className="text-[10px] font-black uppercase tracking-[0.18em] text-ops-emerald/75">Global Knowledge</p>
            <h2 className="mt-1 text-lg font-black text-ops-text">全局知识库</h2>
            <p className="mt-1 text-xs leading-5 text-ops-muted">Agent 运行时会检索这里的知识作为历史参考，并在执行前重新检查当前状态。</p>
          </div>
          <button
            type="button"
            className="rounded-xl border border-ops-border/20 px-3 py-2 text-[10px] font-black text-ops-muted transition hover:border-ops-green/40 hover:text-ops-green active:scale-95"
            onClick={onClose}
          >
            关闭
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-1 py-2">
          {hasKnowledgeRuntimeStats ? (
            <div className="mx-4 mt-2 rounded-2xl border border-ops-emerald/20 bg-ops-emerald/10 px-4 py-3 text-xs text-ops-emerald">
              <div className="font-black">最近一次运行知识库注入</div>
              <div className="mt-1 text-ops-emerald/80">
                命中 {knowledgeEntriesInjected ?? 0} 条知识，注入 {knowledgeContextChars ?? 0} 字符。
              </div>
            </div>
          ) : null}

          {!conversationId ? (
            <div className="mx-4 mt-3 rounded-2xl border border-ops-border/20 bg-ops-panel/35 px-4 py-3 text-xs font-bold text-ops-muted">
              选择或创建会话后，可以从当前会话生成知识草稿；全局搜索和管理不依赖会话。
            </div>
          ) : null}

          <KnowledgeDraftReview
            conversationId={conversationId}
            selectedModel={selectedModel}
            draft={draft}
            draftSourceConversation={draftSourceConversation}
            draftLoading={draftLoading}
            draftError={draftError}
            saving={saving}
            onGenerateDraft={onGenerateDraft}
            onSaveDraft={onSaveDraft}
            onClearDraft={onClearDraft}
            onDraftChange={onDraftChange}
          />

          <KnowledgeBrowser
            entries={entries}
            total={total}
            limit={limit}
            offset={offset}
            loading={loading}
            error={error}
            reindexing={reindexing}
            onSearch={onSearch}
            onDeleteEntry={onDeleteEntry}
            onReindex={onReindex}
          />
        </div>
      </aside>
    </div>
  )
}
