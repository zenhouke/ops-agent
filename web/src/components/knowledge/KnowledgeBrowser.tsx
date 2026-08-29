import { useEffect, useRef, useState } from 'react'
import type {
  KnowledgeAssetRef,
  KnowledgeCommand,
  KnowledgeEntry,
  KnowledgeReindexResponse,
  KnowledgeSearchParams,
  KnowledgeSearchResponse,
  KnowledgeSourceRef,
} from '../../types/ops'

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
}

const PAGE_SIZE = 10

function compactText(value: string | null | undefined, fallback: string) {
  const trimmed = value?.trim() ?? ''
  return trimmed.length > 0 ? trimmed : fallback
}

function formatDate(value: string | null | undefined) {
  if (!value) return '时间未知'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function joinSummary(items: string[], fallback: string) {
  const compactItems = items.map((item) => item.trim()).filter(Boolean)
  return compactItems.length > 0 ? compactItems.join(' · ') : fallback
}

function commandLabel(command: KnowledgeCommand) {
  return [compactText(command.command, '未命名命令'), compactText(command.purpose, ''), compactText(command.outcome, '')].filter(Boolean).join(' / ')
}

function assetLabel(asset: KnowledgeAssetRef) {
  const label = compactText(asset.label, '未命名资产')
  return asset.assetId === null ? label : `${label} #${asset.assetId}`
}

function sourceLabel(source: KnowledgeSourceRef) {
  const eventLabel = source.eventIndex !== null ? `事件 #${source.eventIndex}` : compactText(source.eventType, '来源')
  return [eventLabel, compactText(source.relevance, '')].filter(Boolean).join(' / ')
}

export function KnowledgeBrowser({ entries, total, limit, offset, loading, error, reindexing, onSearch, onDeleteEntry, onReindex }: KnowledgeBrowserProps) {
  const [query, setQuery] = useState('')
  const [tag, setTag] = useState('')
  const [expandedEntryId, setExpandedEntryId] = useState<string | null>(null)
  const hasLoadedRef = useRef(false)
  const [appliedFilters, setAppliedFilters] = useState<KnowledgeSearchParams>({ limit: PAGE_SIZE, offset: 0 })

  useEffect(() => {
    if (hasLoadedRef.current) return
    hasLoadedRef.current = true
    void onSearch({ limit: PAGE_SIZE, offset: 0 })
  }, [onSearch])

  const effectiveLimit = limit > 0 ? limit : PAGE_SIZE
  const currentPage = Math.floor(offset / effectiveLimit) + 1
  const totalPages = Math.max(1, Math.ceil(total / effectiveLimit))

  const handleSearch = (nextOffset = 0, isNewSearch = false) => {
    const nextParams: KnowledgeSearchParams = isNewSearch
      ? { limit: PAGE_SIZE, offset: 0, query: query.trim() || undefined, tag: tag.trim() || undefined }
      : { ...appliedFilters, offset: nextOffset }
    setAppliedFilters(nextParams)
    void onSearch(nextParams)
  }

  const clearFilters = () => {
    setQuery('')
    setTag('')
    const next = { limit: PAGE_SIZE, offset: 0 }
    setAppliedFilters(next)
    void onSearch(next)
  }

  const handleDelete = (entry: KnowledgeEntry) => {
    if (window.confirm(`确定删除知识「${compactText(entry.title, '未命名知识')}」吗？`)) void onDeleteEntry(entry.id)
  }

  return (
    <section className="flex min-h-full flex-1 flex-col" aria-label="知识条目">
      <div className="grid gap-3 border-b border-ops-border/25 pb-4 lg:grid-cols-[minmax(240px,1fr)_minmax(160px,220px)] xl:grid-cols-[minmax(0,1fr)_200px_auto]">
        <label>
          <span className="sr-only">搜索知识</span>
          <input className="field-control h-9 w-full" value={query} placeholder="搜索标题、摘要、问题或处置方案" onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') handleSearch(0, true) }} />
        </label>
        <label>
          <span className="sr-only">筛选标签</span>
          <input className="field-control h-9 w-full" value={tag} placeholder="按标签筛选" onChange={(event) => setTag(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') handleSearch(0, true) }} />
        </label>
        <div className="flex flex-wrap items-center gap-2 lg:col-span-2 xl:col-span-1">
          <button type="button" className="button button-primary h-9 min-w-20 px-4" disabled={loading} onClick={() => handleSearch(0, true)}>{loading ? '搜索中' : '搜索'}</button>
          <button type="button" className="button h-9 px-3" onClick={clearFilters}>重置</button>
          <button type="button" className="button h-9 px-3" disabled={reindexing} onClick={() => void onReindex()}>{reindexing ? '重建中' : '重建索引'}</button>
        </div>
      </div>

      <div className="flex min-h-10 flex-wrap items-center justify-between gap-2 border-b border-ops-border/20 py-2 text-[11px] text-ops-muted">
        <span>共 {total} 条知识</span>
        <span>点击条目查看诊断、处置和来源</span>
      </div>

      {error ? <div className="my-3 border border-ops-danger/30 bg-ops-danger/5 px-3 py-2 text-xs text-ops-danger" role="alert">{error}</div> : null}

      <div className="mt-3 flex-1 space-y-2">
        {entries.length === 0 ? (
          <div className="flex min-h-[240px] flex-1 flex-col items-center justify-center text-center">
            <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-md border border-ops-border/35 text-ops-muted" aria-hidden="true">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5z" /></svg>
            </div>
            <p className="text-xs font-semibold text-ops-text">{loading ? '正在加载知识库' : '暂无匹配知识'}</p>
            <p className="mt-1.5 text-[10px] text-ops-muted/65">可以从当前任务提炼第一条可复用知识。</p>
          </div>
        ) : entries.map((entry) => {
          const entryExpanded = expandedEntryId === entry.id
          return (
            <article key={entry.id} className={`overflow-hidden rounded-md border transition-colors ${entryExpanded ? 'border-ops-border/45 bg-ops-panel/35' : 'border-ops-border/25 bg-ops-deep/20 hover:border-ops-border/40'}`}>
              <div className="flex items-start gap-2 px-3 py-3.5 sm:gap-4 sm:px-4">
                <button type="button" className="min-w-0 flex-1 text-left active:scale-[0.995]" onClick={() => setExpandedEntryId((current) => current === entry.id ? null : entry.id)} aria-expanded={entryExpanded}>
                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                    <svg className="h-3.5 w-3.5 shrink-0 text-ops-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M6 3h9l3 3v15H6z" /><path d="M9 12h6M9 16h4" /></svg>
                    <h3 className="min-w-0 flex-1 truncate text-[13px] font-semibold text-ops-text">{compactText(entry.title, '未命名知识')}</h3>
                    {entry.tags.slice(0, 3).map((item) => <span key={item} className="shrink-0 rounded border border-ops-border/30 px-1.5 py-0.5 text-[10px] text-ops-muted">{item}</span>)}
                  </div>
                  <p className="mt-2 line-clamp-2 pl-[22px] text-xs leading-5 text-ops-muted/80">{compactText(entry.summary, '暂无摘要')}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-2 pl-[22px] text-[10px] text-ops-muted/55">
                    <span className="max-w-full truncate">{compactText(entry.sourceConversation.title, '未知任务')}</span><span>·</span><time dateTime={entry.updatedAt}>{formatDate(entry.updatedAt)}</time>
                  </div>
                </button>
                <button type="button" className="shrink-0 rounded px-2 py-1 text-[10px] text-ops-muted transition-all duration-200 hover:bg-ops-danger/10 hover:text-ops-danger active:scale-95" onClick={() => handleDelete(entry)}>删除</button>
              </div>

              {entryExpanded ? (
                <div className="border-t border-ops-border/15 px-4 py-4 sm:px-6">
                  <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
                    <DetailBlock title="问题" value={entry.problem} fallback="暂无问题描述" />
                    <DetailBlock title="诊断" value={entry.diagnosis} fallback="暂无诊断内容" />
                    <DetailBlock title="处置" value={entry.resolution} fallback="暂无处置方案" />
                  </div>
                  <dl className="mt-4 grid gap-3 border-t border-ops-border/15 pt-3 text-[11px] md:grid-cols-2 xl:grid-cols-3">
                    <SummaryRow title="命令" value={joinSummary(entry.commands.map(commandLabel), '无命令摘要')} />
                    <SummaryRow title="资产" value={joinSummary(entry.assets.map(assetLabel), '无资产摘要')} />
                    <SummaryRow title="来源" value={joinSummary(entry.sources.map(sourceLabel), '无来源摘要')} />
                  </dl>
                </div>
              ) : null}
            </article>
          )
        })}
      </div>

      <footer className="mt-3 flex min-h-12 flex-wrap items-center justify-between gap-2 border-t border-ops-border/25 py-2 text-[11px] text-ops-muted">
        <span>第 {currentPage} / {totalPages} 页</span>
        <div className="flex items-center gap-2">
          <button type="button" className="button h-8 px-3" disabled={offset <= 0 || loading} onClick={() => handleSearch(Math.max(0, offset - effectiveLimit), false)}>上一页</button>
          <button type="button" className="button h-8 px-3" disabled={offset + effectiveLimit >= total || loading} onClick={() => handleSearch(offset + effectiveLimit, false)}>下一页</button>
        </div>
      </footer>
    </section>
  )
}

function DetailBlock({ title, value, fallback }: { title: string; value: string; fallback: string }) {
  return <div><div className="mb-1.5 text-[10px] font-semibold tracking-[0.1em] text-ops-muted/60">{title}</div><p className="whitespace-pre-wrap text-xs leading-5 text-ops-text/85">{compactText(value, fallback)}</p></div>
}

function SummaryRow({ title, value }: { title: string; value: string }) {
  return <div className="min-w-0"><dt className="text-ops-muted/50">{title}</dt><dd className="mt-1 line-clamp-2 text-ops-muted/75">{value}</dd></div>
}
