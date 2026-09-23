import { useEffect } from 'react'
import type { KnowledgeBaseController } from '../../hooks/useKnowledgeBase'
import { useKnowledgeExtraction } from '../../hooks/useKnowledgeExtraction'
import { KnowledgeBrowser } from './KnowledgeBrowser'

type KnowledgeWorkspaceProps = {
  conversationId: string | null
  conversationTitle: string
  selectedModel: string
  knowledge: KnowledgeBaseController
  onOpenConversation: (conversationId: string) => void
}

export function KnowledgeWorkspace({ conversationId, conversationTitle, selectedModel, knowledge, onOpenConversation }: KnowledgeWorkspaceProps) {
  const extraction = useKnowledgeExtraction(conversationId)
  const refresh = knowledge.refresh
  useEffect(() => {
    if (extraction.completionKey) void refresh()
  }, [extraction.completionKey, refresh])
  return (
    <section className="flex h-full min-h-0 flex-col bg-ops-bg" aria-labelledby="knowledge-workspace-title">
      <header className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-ops-border/30 bg-ops-deep/45 px-5 py-3">
        <div><h1 id="knowledge-workspace-title" className="text-sm font-semibold text-ops-text">知识库</h1><p className="mt-1 text-[11px] text-ops-muted">按主题沉淀 Markdown 文件，持续补充知识并保留会话来源。</p></div>
        <button type="button" className="button px-3 py-2 text-xs" disabled={!conversationId || extraction.busy} title={conversationTitle ? `从「${conversationTitle}」提炼` : '请先选择会话'} onClick={() => void extraction.start(selectedModel || null)}>{extraction.busy ? '后台提炼中…' : '提炼当前会话'}</button>
      </header>
      {extraction.message ? <p role={extraction.failed ? 'alert' : 'status'} className={`border-b border-ops-border/25 px-5 py-2 text-xs ${extraction.failed ? 'text-ops-danger' : 'text-ops-muted'}`}>{extraction.message}</p> : null}
      <KnowledgeBrowser entries={knowledge.entries} total={knowledge.total} limit={knowledge.limit} offset={knowledge.offset} loading={knowledge.loading} error={knowledge.error} reindexing={knowledge.reindexing} onSearch={knowledge.search} onDeleteEntry={knowledge.deleteEntry} onReindex={knowledge.reindex} onOpenConversation={onOpenConversation} />
    </section>
  )
}
