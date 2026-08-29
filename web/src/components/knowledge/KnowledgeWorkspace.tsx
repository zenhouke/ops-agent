import { useEffect, useState } from 'react'
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

type KnowledgeWorkspaceProps = {
  conversationId: string | null
  conversationTitle: string
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
  onSearch: (params?: KnowledgeSearchParams) => Promise<KnowledgeSearchResponse>
  onDeleteEntry: (entryId: string) => Promise<boolean>
  onReindex: () => Promise<KnowledgeReindexResponse | null>
  onGenerateDraft: (conversationId: string, payload?: { maxSourceEvents?: number; modelName?: string | null }) => Promise<KnowledgeGenerateDraftResponse | null>
  onSaveDraft: (payload?: Partial<KnowledgeEntryPayload>) => Promise<KnowledgeEntry | null>
  onClearDraft: () => void
  onDraftChange: (draft: KnowledgeDraft | null) => void
}

type KnowledgeTab = 'library' | 'draft'

export function KnowledgeWorkspace(props: KnowledgeWorkspaceProps) {
  const [activeTab, setActiveTab] = useState<KnowledgeTab>('library')
  const hasRuntimeStats = props.knowledgeEntriesInjected !== undefined || props.knowledgeContextChars !== undefined

  useEffect(() => {
    if (props.draftLoading || props.draftError) setActiveTab('draft')
  }, [props.draftError, props.draftLoading])

  return (
    <section className="flex h-full min-h-0 flex-col bg-ops-bg" aria-labelledby="knowledge-workspace-title">
      <header className="shrink-0 border-b border-ops-border/30 bg-ops-deep/45 px-4 pt-4 sm:px-6">
        <div className="flex min-h-12 flex-wrap items-start justify-between gap-x-6 gap-y-3">
          <div className="min-w-0">
            <div className="text-[9px] font-semibold tracking-[0.12em] text-ops-muted/55">工作区</div>
            <h1 id="knowledge-workspace-title" className="mt-0.5 text-base font-semibold text-ops-text">知识库</h1>
            <p className="mt-1 text-xs leading-5 text-ops-muted/70">沉淀经过审核的运维经验，并在后续任务中按需检索。</p>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2 text-[11px] text-ops-muted/70">
            <span className="rounded-md border border-ops-border/30 bg-ops-bg/35 px-2.5 py-1.5"><strong className="mr-1 font-semibold text-ops-text">{props.total}</strong>条知识</span>
            {hasRuntimeStats ? <span className="rounded-md border border-ops-border/30 bg-ops-bg/35 px-2.5 py-1.5">最近任务命中 <strong className="mx-1 font-semibold text-ops-text">{props.knowledgeEntriesInjected ?? 0}</strong> 条 · {props.knowledgeContextChars ?? 0} 字符</span> : null}
          </div>
        </div>
        <nav className="mt-2 flex h-10 items-end gap-1 overflow-x-auto" aria-label="知识库视图">
          <KnowledgeTabButton active={activeTab === 'library'} onClick={() => setActiveTab('library')}>知识条目</KnowledgeTabButton>
          <KnowledgeTabButton active={activeTab === 'draft'} onClick={() => setActiveTab('draft')}>
            从当前任务提炼{props.draft ? <span className="ml-1.5 h-1.5 w-1.5 rounded-full bg-ops-warning" aria-label="有未保存草稿" /> : null}
          </KnowledgeTabButton>
        </nav>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto flex min-h-full w-full max-w-[1180px] flex-col p-4 sm:p-6">
          {activeTab === 'library' ? (
            <KnowledgeBrowser entries={props.entries} total={props.total} limit={props.limit} offset={props.offset} loading={props.loading} error={props.error} reindexing={props.reindexing} onSearch={props.onSearch} onDeleteEntry={props.onDeleteEntry} onReindex={props.onReindex} />
          ) : (
            <KnowledgeDraftReview conversationId={props.conversationId} selectedModel={props.selectedModel} draft={props.draft} draftSourceConversation={props.draftSourceConversation ?? (props.conversationId ? { id: props.conversationId, title: props.conversationTitle, updatedAt: null } : null)} draftLoading={props.draftLoading} draftError={props.draftError} saving={props.saving} onGenerateDraft={props.onGenerateDraft} onSaveDraft={props.onSaveDraft} onClearDraft={props.onClearDraft} onDraftChange={props.onDraftChange} />
          )}
        </div>
      </div>
    </section>
  )
}

function KnowledgeTabButton({ active, children, onClick }: { active: boolean; children: React.ReactNode; onClick: () => void }) {
  return <button type="button" className={`flex h-10 shrink-0 items-center border-b-2 px-3 text-xs font-medium transition-all duration-200 active:scale-95 ${active ? 'border-ops-text text-ops-text' : 'border-transparent text-ops-muted hover:text-ops-text'}`} onClick={onClick}>{children}</button>
}
