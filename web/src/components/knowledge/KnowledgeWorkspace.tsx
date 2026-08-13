import { useState } from 'react'
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
  const [activeTab, setActiveTab] = useState<KnowledgeTab>(props.draft ? 'draft' : 'library')
  const hasRuntimeStats = props.knowledgeEntriesInjected !== undefined || props.knowledgeContextChars !== undefined

  return (
    <section className="flex h-full min-h-0 flex-col bg-ops-bg" aria-labelledby="knowledge-workspace-title">
      <header className="shrink-0 border-b border-ops-border/30 bg-ops-deep/45 px-6 pt-3">
        <div className="flex min-h-12 items-start justify-between gap-6">
          <div>
            <div className="text-[9px] font-semibold tracking-[0.12em] text-ops-muted/55">工作区</div>
            <h1 id="knowledge-workspace-title" className="mt-0.5 text-[15px] font-semibold text-ops-text">知识库</h1>
            <p className="mt-0.5 text-[10px] text-ops-muted/65">沉淀经过审核的运维经验，并在后续任务中按需检索。</p>
          </div>
          <div className="flex items-center gap-4 text-[10px] text-ops-muted/60">
            <span><strong className="mr-1 font-semibold text-ops-text">{props.total}</strong>条知识</span>
            {hasRuntimeStats ? <span>最近任务命中 <strong className="mx-1 font-semibold text-ops-text">{props.knowledgeEntriesInjected ?? 0}</strong> 条 · {props.knowledgeContextChars ?? 0} 字符</span> : null}
          </div>
        </div>
        <nav className="flex h-9 items-end gap-1" aria-label="知识库视图">
          <KnowledgeTabButton active={activeTab === 'library'} onClick={() => setActiveTab('library')}>知识条目</KnowledgeTabButton>
          <KnowledgeTabButton active={activeTab === 'draft'} onClick={() => setActiveTab('draft')}>
            从当前任务提炼{props.draft ? <span className="ml-1.5 h-1.5 w-1.5 rounded-full bg-ops-warning" aria-label="有未保存草稿" /> : null}
          </KnowledgeTabButton>
        </nav>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[1180px] p-6">
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
  return <button type="button" className={`flex h-9 items-center border-b-2 px-3 text-[10px] font-medium transition-all duration-200 active:scale-95 ${active ? 'border-ops-text text-ops-text' : 'border-transparent text-ops-muted hover:text-ops-text'}`} onClick={onClick}>{children}</button>
}
