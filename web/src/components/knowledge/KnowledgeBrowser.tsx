import { useEffect, useMemo, useRef, useState } from 'react'
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
  if (!value) {
    return '时间未知'
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }

  return date.toLocaleString()
}

function joinSummary(items: string[], fallback: string) {
  const compactItems = items.map((item) => item.trim()).filter(Boolean)
  return compactItems.length > 0 ? compactItems.join(' · ') : fallback
}

function commandLabel(command: KnowledgeCommand) {
  const commandText = compactText(command.command, '未命名命令')
  const purpose = compactText(command.purpose, '')
  const outcome = compactText(command.outcome, '')
  return [commandText, purpose, outcome].filter(Boolean).join(' / ')
}

function assetLabel(asset: KnowledgeAssetRef) {
  const label = compactText(asset.label, '未命名资产')
  return asset.assetId === null ? label : `${label} #${asset.assetId}`
}

function sourceLabel(source: KnowledgeSourceRef) {
  const eventLabel = source.eventIndex !== null ? `事件 #${source.eventIndex}` : compactText(source.eventType, '来源')
  const relevance = compactText(source.relevance, '')
  return [eventLabel, relevance].filter(Boolean).join(' / ')
}

export function KnowledgeBrowser({
  entries,
  total,
  limit,
  offset,
  loading,
  error,
  reindexing,
  onSearch,
  onDeleteEntry,
  onReindex,
}: KnowledgeBrowserProps) {
  const [expanded, setExpanded] = useState(false)
  const [query, setQuery] = useState('')
  const [tag, setTag] = useState('')
  const [expandedEntryId, setExpandedEntryId] = useState<string | null>(null)
  const hasLoadedRef = useRef(false)

  const effectiveLimit = limit > 0 ? limit : PAGE_SIZE
  const currentPage = Math.floor(offset / effectiveLimit) + 1
  const totalPages = Math.max(1, Math.ceil(total / effectiveLimit))
  const canGoPrevious = offset > 0 && !loading
  const canGoNext = offset + effectiveLimit < total && !loading

  const [appliedFilters, setAppliedFilters] = useState<KnowledgeSearchParams>({
    limit: PAGE_SIZE,
    offset: 0,
  })

  useEffect(() => {
    if (!expanded || hasLoadedRef.current) {
      return
    }

    hasLoadedRef.current = true
    void onSearch({ limit: PAGE_SIZE, offset: 0 })
  }, [expanded, onSearch])

  const handleSearch = (nextOffset = 0, isNewSearch = false) => {
    const nextParams: KnowledgeSearchParams = isNewSearch
      ? {
          limit: PAGE_SIZE,
          offset: 0,
          query: query.trim() || undefined,
          tag: tag.trim() || undefined,
        }
      : {
          ...appliedFilters,
          offset: nextOffset,
        }

    if (isNewSearch) {
      setAppliedFilters(nextParams)
    } else {
      setAppliedFilters((current) => ({ ...current, offset: nextOffset }))
    }

    void onSearch(nextParams)
  }

  const handleDelete = (entry: KnowledgeEntry) => {
    if (!window.confirm(`确定删除知识「${compactText(entry.title, '未命名知识')}」吗？`)) {
      return
    }

    void onDeleteEntry(entry.id)
  }

  return (
    <section className="relative z-10 mx-4 mt-3 rounded-2xl border border-ops-border/20 bg-ops-panel/45 shadow-xl shadow-black/10 backdrop-blur">
      <div className="flex items-center gap-3 px-4 py-3">
        <button
          type="button"
          className="flex min-w-0 flex-1 items-center gap-3 text-left"
          onClick={() => setExpanded((current) => !current)}
          aria-expanded={expanded}
        >
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-ops-emerald/25 bg-ops-emerald/10 text-ops-emerald">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5z" /></svg>
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-[10px] font-black uppercase tracking-[0.16em] text-ops-muted/70">知识库</span>
            <span className="block truncate text-sm font-black text-ops-text">{expanded ? `共 ${total} 条知识` : '浏览已保存知识'}</span>
          </span>
        </button>

        <button
          type="button"
          className="shrink-0 rounded-xl border border-ops-border/20 px-3 py-2 text-[10px] font-black text-ops-muted transition hover:border-ops-emerald/40 hover:text-ops-emerald active:scale-95"
          onClick={() => setExpanded((current) => !current)}
        >
          {expanded ? '收起' : '展开'}
        </button>
      </div>

      {expanded ? (
        <div className="space-y-3 border-t border-ops-border/15 px-4 py-4">
          <div className="grid gap-2 xl:grid-cols-[minmax(0,1fr)_180px_auto]">
            <input
              className="rounded-xl border border-ops-border/20 bg-ops-bg/70 px-3 py-2 text-sm text-ops-text outline-none transition placeholder:text-ops-muted/45 focus:border-ops-emerald/50"
              value={query}
              placeholder="搜索标题、摘要或内容"
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  handleSearch(0, true)
                }
              }}
            />
            <input
              className="rounded-xl border border-ops-border/20 bg-ops-bg/70 px-3 py-2 text-sm text-ops-text outline-none transition placeholder:text-ops-muted/45 focus:border-ops-emerald/50"
              value={tag}
              placeholder="标签"
              onChange={(event) => setTag(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  handleSearch(0, true)
                }
              }}
            />
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                className="rounded-xl border border-ops-emerald/30 bg-ops-emerald/10 px-3 py-2 text-[10px] font-black tracking-[0.08em] text-ops-emerald transition hover:bg-ops-emerald/20 active:scale-95 disabled:cursor-not-allowed disabled:opacity-45"
                disabled={loading}
                onClick={() => handleSearch(0, true)}
              >
                {loading ? '搜索中' : '搜索'}
              </button>
              <button
                type="button"
                className="rounded-xl border border-ops-border/20 px-3 py-2 text-[10px] font-black text-ops-muted transition hover:border-ops-cyan/40 hover:text-ops-cyan active:scale-95 disabled:cursor-not-allowed disabled:opacity-45"
                disabled={reindexing}
                onClick={() => void onReindex()}
              >
                {reindexing ? '重建中' : '重建索引'}
              </button>
            </div>
          </div>

          {error ? (
            <div className="rounded-xl border border-ops-danger/35 bg-ops-danger/10 px-3 py-2 text-xs font-bold text-ops-danger" role="alert">
              {error}
            </div>
          ) : null}

          <div className="space-y-2">
            {entries.length === 0 ? (
              <div className="rounded-xl border border-dashed border-ops-border/20 px-3 py-6 text-center text-xs font-bold text-ops-muted/60">
                {loading ? '正在加载知识库' : '暂无匹配知识'}
              </div>
            ) : entries.map((entry) => {
              const entryExpanded = expandedEntryId === entry.id
              return (
                <article key={entry.id} className="rounded-xl border border-ops-border/15 bg-ops-bg/45">
                  <div className="flex gap-3 px-3 py-3">
                    <button
                      type="button"
                      className="min-w-0 flex-1 text-left"
                      onClick={() => setExpandedEntryId((current) => current === entry.id ? null : entry.id)}
                      aria-expanded={entryExpanded}
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="truncate text-sm font-black text-ops-text">{compactText(entry.title, '未命名知识')}</h3>
                        {entry.tags.map((item) => (
                          <span key={item} className="rounded-full border border-ops-border/20 px-2 py-0.5 text-[10px] font-bold text-ops-muted">{item}</span>
                        ))}
                      </div>
                      <p className="mt-1 line-clamp-2 text-xs leading-5 text-ops-muted">{compactText(entry.summary, '暂无摘要')}</p>
                      <div className="mt-2 flex flex-wrap gap-2 text-[10px] font-bold text-ops-muted/70">
                        <span>{compactText(entry.sourceConversation.title, '未知会话')}</span>
                        <span>{formatDate(entry.updatedAt)}</span>
                      </div>
                    </button>
                    <button
                      type="button"
                      className="h-9 shrink-0 rounded-xl border border-ops-border/20 px-3 text-[10px] font-black text-ops-muted transition hover:border-ops-danger/40 hover:text-ops-danger active:scale-95"
                      onClick={() => handleDelete(entry)}
                    >
                      删除
                    </button>
                  </div>

                  {entryExpanded ? (
                    <div className="space-y-3 border-t border-ops-border/15 px-3 py-3">
                      <div className="grid gap-3 lg:grid-cols-3">
                        <DetailBlock title="问题" value={entry.problem} fallback="暂无问题描述" />
                        <DetailBlock title="诊断" value={entry.diagnosis} fallback="暂无诊断内容" />
                        <DetailBlock title="处置" value={entry.resolution} fallback="暂无处置方案" />
                      </div>
                      <div className="grid gap-3 xl:grid-cols-3">
                        <SummaryBlock title="命令" value={joinSummary(entry.commands.map(commandLabel), '无命令摘要')} />
                        <SummaryBlock title="资产" value={joinSummary(entry.assets.map(assetLabel), '无资产摘要')} />
                        <SummaryBlock title="来源" value={joinSummary(entry.sources.map(sourceLabel), '无来源摘要')} />
                      </div>
                    </div>
                  ) : null}
                </article>
              )
            })}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-ops-border/15 pt-3 text-[10px] font-black text-ops-muted">
            <span>第 {currentPage} / {totalPages} 页</span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="rounded-xl border border-ops-border/20 px-3 py-2 transition hover:border-ops-emerald/40 hover:text-ops-emerald active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
                disabled={!canGoPrevious}
                onClick={() => handleSearch(Math.max(0, offset - effectiveLimit), false)}
              >
                上一页
              </button>
              <button
                type="button"
                className="rounded-xl border border-ops-border/20 px-3 py-2 transition hover:border-ops-emerald/40 hover:text-ops-emerald active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
                disabled={!canGoNext}
                onClick={() => handleSearch(offset + effectiveLimit, false)}
              >
                下一页
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  )
}

type DetailBlockProps = {
  title: string
  value: string
  fallback: string
}

function DetailBlock({ title, value, fallback }: DetailBlockProps) {
  return (
    <div className="rounded-xl border border-ops-border/15 bg-ops-panel/35 p-3">
      <div className="mb-1 text-[10px] font-black uppercase tracking-[0.14em] text-ops-muted/70">{title}</div>
      <p className="text-xs leading-5 text-ops-text/85">{compactText(value, fallback)}</p>
    </div>
  )
}

type SummaryBlockProps = {
  title: string
  value: string
}

function SummaryBlock({ title, value }: SummaryBlockProps) {
  return (
    <div className="rounded-xl border border-ops-border/15 bg-ops-bg/35 p-3">
      <div className="mb-1 text-[10px] font-black uppercase tracking-[0.14em] text-ops-muted/70">{title}</div>
      <p className="line-clamp-3 text-xs leading-5 text-ops-muted">{value}</p>
    </div>
  )
}
