import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { KnowledgeVersionHistory } from './KnowledgeVersionHistory'
import { getKnowledgeMarkdown } from '../../api/knowledge'
import type { KnowledgeEntry, KnowledgeReindexResponse, KnowledgeSearchParams, KnowledgeSearchResponse } from '../../types/ops'

type KnowledgeBrowserProps = {
  entries: KnowledgeEntry[]
  total: number
  limit: number
  offset: number
  loading: boolean
  error: string | null
  reindexing: boolean
  onSearch: (params?: KnowledgeSearchParams) => Promise<KnowledgeSearchResponse>
  onDeleteEntry: (entryId: string) => Promise<boolean>
  onReindex: () => Promise<KnowledgeReindexResponse | null>
  onOpenConversation: (conversationId: string) => void
}

const PAGE_SIZE = 30

export function KnowledgeBrowser({ entries, total, limit, offset, loading, error, reindexing, onSearch, onDeleteEntry, onReindex, onOpenConversation }: KnowledgeBrowserProps) {
  const [query, setQuery] = useState('')
  const [tag, setTag] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [filters, setFilters] = useState<KnowledgeSearchParams>({ limit: PAGE_SIZE, offset: 0 })
  const [document, setDocument] = useState<{ id: string; text: string; error: string | null } | null>(null)
  const selected = entries.find((entry) => entry.id === selectedId) ?? entries[0] ?? null
  const selectedEntryId = selected?.id
  const selectedUpdatedAt = selected?.updatedAt
  const markdown = document?.id === selectedEntryId ? document : null

  useEffect(() => { void onSearch(filters) }, [onSearch, filters])
  useEffect(() => {
    if (!selectedEntryId) return
    let active = true
    void getKnowledgeMarkdown(selectedEntryId).then((text) => {
      if (active) setDocument({ id: selectedEntryId, text, error: null })
    }).catch((reason: unknown) => {
      if (active) setDocument({ id: selectedEntryId, text: '', error: reason instanceof Error ? reason.message : '读取文件失败' })
    })
    return () => { active = false }
  }, [selectedEntryId, selectedUpdatedAt])

  const sourceIds = [...new Set([selected?.sourceConversation.id, ...(selected?.sources.map((source) => source.conversationId) ?? [])].filter((id): id is string => Boolean(id)))]
  const pageSize = limit || PAGE_SIZE
  const download = () => {
    if (!selected || !markdown?.text) return
    const url = URL.createObjectURL(new Blob([markdown.text], { type: 'text/markdown;charset=utf-8' }))
    const link = window.document.createElement('a')
    link.href = url
    link.download = `${selected.title.replace(/[\\/:*?"<>|]/g, '_') || selected.id}.md`
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  return (
    <section className="flex min-h-0 flex-1 flex-col" aria-label="知识文件工作区">
      {error ? <p className="border-b border-ops-danger/30 p-3 text-xs text-ops-danger" role="alert">{error}</p> : null}
      <div className="grid min-h-0 flex-1 grid-cols-1 overflow-auto md:grid-cols-[240px_minmax(0,1fr)] xl:grid-cols-[260px_minmax(0,1fr)_250px] md:overflow-hidden">
        <aside className="flex min-h-0 flex-col border-r border-ops-border/30 bg-ops-deep/30" aria-label="文件列表">
          <form className="space-y-2 border-b border-ops-border/25 p-3" onSubmit={(event) => { event.preventDefault(); setFilters({ query: query.trim(), tag: tag.trim(), limit: PAGE_SIZE, offset: 0 }) }}>
            <div className="flex items-center justify-between text-xs font-semibold text-ops-text"><span>知识文件</span><span className="text-ops-muted">{total}</span></div>
            <input aria-label="搜索知识文件" className="field-control h-8 w-full" placeholder="搜索文件和内容…" value={query} onChange={(event) => setQuery(event.target.value)} />
            <div className="flex gap-1"><input aria-label="筛选知识标签" className="field-control h-8 min-w-0 flex-1" placeholder="标签" value={tag} onChange={(event) => setTag(event.target.value)} /><button className="button px-2 text-xs" disabled={loading}>搜索</button></div>
          </form>
          <nav className="min-h-[140px] flex-1 overflow-y-auto p-2" aria-label="知识文件">
            {entries.map((entry) => <button key={entry.id} type="button" aria-current={entry.id === selected?.id ? 'page' : undefined} className={`mb-1 w-full rounded px-3 py-2.5 text-left ${entry.id === selected?.id ? 'bg-ops-text/10 text-ops-text' : 'text-ops-muted hover:bg-ops-text/5'}`} onClick={() => setSelectedId(entry.id)}><span className="block truncate text-xs font-medium">{entry.title || '未命名知识'}.md</span><span className="mt-1 block truncate text-[10px] opacity-60">{entry.summary || '无摘要'}</span></button>)}
            {!entries.length ? <p className="p-3 text-xs text-ops-muted">{loading ? '正在加载…' : '暂无知识文件，可从会话中提炼。'}</p> : null}
          </nav>
          <div className="flex items-center justify-between border-t border-ops-border/25 p-2 text-[11px] text-ops-muted"><button type="button" className="button px-2" disabled={loading || offset <= 0} onClick={() => setFilters({ ...filters, offset: Math.max(0, offset - pageSize) })}>上一页</button><span>{Math.floor(offset / pageSize) + 1} / {Math.max(1, Math.ceil(total / pageSize))}</span><button type="button" className="button px-2" disabled={loading || offset + pageSize >= total} onClick={() => setFilters({ ...filters, offset: offset + pageSize })}>下一页</button></div>
          <button type="button" className="border-t border-ops-border/25 p-2 text-[11px] text-ops-muted" disabled={reindexing} onClick={() => void onReindex()}>{reindexing ? '重建中…' : '重建检索索引'}</button>
        </aside>
        <main className="min-h-[300px] min-w-0 overflow-y-auto bg-ops-bg" aria-label="Markdown 正文">
          {selected ? <>
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-ops-border/25 px-5 py-3 text-xs"><span className="truncate text-ops-muted">{selected.title}.md</span><div className="flex gap-3"><button type="button" className="text-ops-muted hover:text-ops-text" disabled={!markdown?.text} onClick={download}>导出 Markdown</button><button type="button" className="text-ops-muted hover:text-ops-danger" onClick={() => { if (window.confirm(`确定删除知识文件「${selected.title}」吗？`)) void onDeleteEntry(selected.id) }}>删除</button></div></div>
            {markdown?.error ? <p role="alert" className="p-5 text-sm text-ops-danger">{markdown.error}</p> : <article className="mx-auto max-w-[850px] px-6 py-7 text-sm leading-7 text-ops-text [overflow-wrap:anywhere] [&_h1]:mb-6 [&_h1]:text-2xl [&_h1]:font-semibold [&_h2]:mb-3 [&_h2]:mt-8 [&_h2]:text-lg [&_h2]:font-semibold [&_h3]:mb-2 [&_h3]:mt-5 [&_h3]:font-semibold [&_p]:my-3 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_pre]:overflow-auto [&_pre]:rounded [&_pre]:bg-ops-deep [&_pre]:p-4 [&_blockquote]:border-l-2 [&_blockquote]:border-ops-border [&_blockquote]:pl-4 [&_blockquote]:text-ops-muted [&_a]:text-ops-cyan [&_table]:block [&_table]:overflow-auto [&_td]:border [&_td]:border-ops-border/30 [&_td]:p-2 [&_th]:border [&_th]:border-ops-border/30 [&_th]:p-2"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{ img: ({ alt }) => <span>{alt || '图片'}</span> }}>{markdown?.text ?? '正在读取文件…'}</ReactMarkdown></article>}
          </> : <div className="flex h-full items-center justify-center p-8 text-sm text-ops-muted">选择左侧文件阅读知识正文</div>}
        </main>
        <aside className="overflow-y-auto border-t border-ops-border/30 bg-ops-deep/20 p-4 md:col-span-2 xl:col-span-1 xl:border-l xl:border-t-0" aria-label="来源关联">
          {selected ? <KnowledgeVersionHistory key={selected.id} entryId={selected.id} updatedAt={selected.updatedAt} onRestored={() => onSearch(filters)} /> : null}
          <h2 className="text-xs font-semibold text-ops-text">来源关联</h2>
          {selected ? <>
            <p className="mt-3 text-[11px] text-ops-muted">更新于 {new Date(selected.updatedAt).toLocaleString('zh-CN')}</p>
            <div className="mt-3 flex flex-wrap gap-1">{selected.tags.map((value) => <button type="button" key={value} className="rounded bg-ops-text/5 px-2 py-1 text-[10px] text-ops-muted" onClick={() => { setTag(value); setQuery(''); setFilters({ tag: value, limit: PAGE_SIZE, offset: 0 }) }}>#{value}</button>)}</div>
            <h3 className="mb-2 mt-6 text-[11px] font-semibold text-ops-muted">关联会话 · {sourceIds.length}</h3>
            {sourceIds.map((id) => <button type="button" key={id} className="mb-2 block w-full break-all rounded border border-ops-border/25 p-2 text-left text-xs text-ops-cyan hover:bg-ops-text/5" onClick={() => onOpenConversation(id)}>{id === selected.sourceConversation.id ? selected.sourceConversation.title || id : id}<span className="mt-1 block text-[10px] text-ops-muted">打开来源会话 ↗</span></button>)}
            <h3 className="mb-2 mt-6 text-[11px] font-semibold text-ops-muted">证据摘录</h3>
            {selected.sources.filter((source) => source.quote || source.relevance).map((source, index) => <div key={index} className="mb-3 border-l border-ops-border/40 pl-3 text-[11px] leading-5 text-ops-muted"><p>来源 {index + 1}</p>{source.quote ? <blockquote className="whitespace-pre-wrap break-words">{source.quote}</blockquote> : null}{source.relevance ? <p className="mt-1 opacity-70">{source.relevance}</p> : null}</div>)}
          </> : <p className="mt-3 text-xs text-ops-muted">选中文件后查看关联会话和证据。</p>}
        </aside>
      </div>
    </section>
  )
}
