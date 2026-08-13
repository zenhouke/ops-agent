import { useMemo } from 'react'
import { useAppearance } from '../../hooks/useAppearance'
import type { ConversationSummary, EventItem } from '../../types/ops'

type ConversationRunBadge = {
  conversationId: string
  status: 'running' | 'needs_approval' | 'completed' | 'failed'
  hasUnread: boolean
}

type ConversationListProps = {
  items: ConversationSummary[]
  activeConversationId: string | null
  backgroundRun: ConversationRunBadge | null
  onSelect: (conversationId: string) => void
  onDelete: (conversationId: string) => void
}

type StatusMeta = {
  label: string
  dotClassName: string
  textClassName: string
}

type EventKind = EventItem['kind']
type KnownEventKind = EventKind | 'approval' | 'output' | 'status'
type GroupKey = 'today' | 'yesterday' | 'earlier'

const KNOWN_EVENT_KIND_SET: ReadonlySet<KnownEventKind> = new Set<KnownEventKind>([
  'delta',
  'plan',
  'approval_required',
  'approval_decision',
  'command_start',
  'command_chunk',
  'command_end',
  'terminal_status',
  'final',
  'error',
  'user',
  'approval',
  'output',
  'status',
])

function normalizeStatusKind(kind: string | null): KnownEventKind | null {
  if (!kind) return null
  return KNOWN_EVENT_KIND_SET.has(kind as KnownEventKind) ? (kind as KnownEventKind) : null
}

function startOfDay(value: Date) {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime()
}

function getGroupKey(value: string, todayStart: number): GroupKey {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'earlier'
  const dayDifference = Math.round((todayStart - startOfDay(date)) / 86_400_000)
  if (dayDifference <= 0) return 'today'
  if (dayDifference === 1) return 'yesterday'
  return 'earlier'
}

export function ConversationList({ items, activeConversationId, backgroundRun, onSelect, onDelete }: ConversationListProps) {
  const { language, t } = useAppearance()
  const timeFormatter = useMemo(() => new Intl.DateTimeFormat(language, {
    hour: '2-digit',
    minute: '2-digit',
  }), [language])
  const dateTimeFormatter = useMemo(() => new Intl.DateTimeFormat(language, {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }), [language])
  const todayStart = startOfDay(new Date())

  const groupedItems = useMemo(() => {
    const groups: Record<GroupKey, ConversationSummary[]> = { today: [], yesterday: [], earlier: [] }
    items.forEach((item) => groups[getGroupKey(item.updatedAt, todayStart)].push(item))
    return groups
  }, [items, todayStart])

  function getStatusMeta(item: ConversationSummary): StatusMeta {
    const run = backgroundRun?.conversationId === item.id ? backgroundRun : null
    if (run?.status === 'needs_approval') return { label: t('conversation.statusNeedsApproval'), dotClassName: 'bg-ops-warning', textClassName: 'text-ops-warning' }
    if (run?.status === 'failed') return { label: t('conversation.statusFailed'), dotClassName: 'bg-ops-danger', textClassName: 'text-ops-danger' }
    if (run?.status === 'running') return { label: run.hasUnread ? t('conversation.statusNewOutput') : t('conversation.statusRunning'), dotClassName: 'bg-ops-text', textClassName: 'text-ops-text' }
    if (run?.status === 'completed') return { label: t('conversation.statusCompleted'), dotClassName: 'bg-ops-text/70', textClassName: 'text-ops-muted' }

    switch (normalizeStatusKind(item.lastEventKind)) {
      case 'approval_required':
      case 'approval':
        return { label: t('conversation.statusNeedsApproval'), dotClassName: 'bg-ops-warning', textClassName: 'text-ops-warning' }
      case 'error':
        return { label: t('conversation.statusFailed'), dotClassName: 'bg-ops-danger', textClassName: 'text-ops-danger' }
      case 'final':
        return { label: t('conversation.statusCompleted'), dotClassName: 'bg-ops-text/70', textClassName: 'text-ops-muted' }
      case 'command_end':
      case 'output':
        return { label: t('conversation.statusExecuted'), dotClassName: 'bg-ops-text/70', textClassName: 'text-ops-muted' }
      case 'command_start':
      case 'command_chunk':
      case 'delta':
        return { label: t('conversation.statusRunning'), dotClassName: 'bg-ops-text', textClassName: 'text-ops-text' }
      case 'plan':
        return { label: t('conversation.statusPlanning'), dotClassName: 'bg-ops-text/70', textClassName: 'text-ops-muted' }
      case 'user':
        return { label: t('conversation.statusPending'), dotClassName: 'bg-ops-muted/55', textClassName: 'text-ops-muted/75' }
      default:
        return {
          label: item.eventCount === 0 ? t('conversation.statusReady') : t('conversation.statusUpdated'),
          dotClassName: 'bg-ops-muted/55',
          textClassName: 'text-ops-muted/75',
        }
    }
  }

  const groupLabels: Record<GroupKey, string> = {
    today: t('conversation.groupToday'),
    yesterday: t('conversation.groupYesterday'),
    earlier: t('conversation.groupEarlier'),
  }

  return (
    <div className="flex h-full flex-col bg-ops-bg" aria-label={t('conversation.taskHistory')}>
      <div className="flex-1 overflow-y-auto px-2 pb-3 pt-1.5">
        {items.length > 0 ? (
          (Object.keys(groupedItems) as GroupKey[]).map((groupKey) => {
            const groupItems = groupedItems[groupKey]
            if (groupItems.length === 0) return null

            return (
              <section key={groupKey} className="mb-3" aria-labelledby={`conversation-group-${groupKey}`}>
                <div className="flex h-7 items-center gap-2 px-2" id={`conversation-group-${groupKey}`}>
                  <span className="text-[10px] font-semibold tracking-[0.08em] text-ops-muted/65">{groupLabels[groupKey]}</span>
                  <span className="h-px flex-1 bg-ops-border/20" aria-hidden="true" />
                </div>
                <ul className="space-y-0.5" role="list">
                  {groupItems.map((item) => {
                    const isActive = item.id === activeConversationId
                    const isUntitled = !item.title || item.title.trim() === '' || item.title.trim() === 'New'
                    const displayTitle = isUntitled ? t('conversation.untitledTask') : item.title
                    const status = getStatusMeta(item)
                    const updatedDate = new Date(item.updatedAt)
                    const formattedTime = Number.isNaN(updatedDate.getTime())
                      ? item.updatedAt
                      : (groupKey === 'earlier' ? dateTimeFormatter : timeFormatter).format(updatedDate)

                    return (
                      <li key={item.id} className="group relative">
                        <button
                          type="button"
                          className={`relative w-full rounded-md border px-2.5 py-2.5 text-left transition-all duration-200 active:scale-[0.99] ${isActive
                            ? 'border-ops-text/25 bg-ops-panel/80'
                            : 'border-transparent hover:border-ops-border/30 hover:bg-ops-panel/45'
                          }`}
                          onClick={() => onSelect(item.id)}
                          title={displayTitle}
                        >
                          <span className={`absolute bottom-2 left-0 top-2 w-0.5 rounded-r ${isActive ? 'bg-ops-text' : 'bg-transparent'}`} aria-hidden="true" />
                          <div className="flex items-start gap-2 pr-5">
                            <svg className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${isActive ? 'text-ops-text' : 'text-ops-muted/55'}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                              <path d="M6 3h9l3 3v15H6z" /><path d="M15 3v4h4M9 11h6M9 15h4" />
                            </svg>
                            <span className={`min-w-0 truncate text-[12px] leading-4 ${isActive ? 'font-semibold text-ops-text' : 'font-medium text-ops-text/82'}`}>
                              {displayTitle}
                            </span>
                          </div>
                          <div className="mt-2 flex min-w-0 items-center gap-1.5 pl-[22px] text-[9px] text-ops-muted/60">
                            <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${status.dotClassName}`} aria-hidden="true" />
                            <span className={`shrink-0 font-medium ${status.textClassName}`}>{status.label}</span>
                            <span aria-hidden="true">·</span>
                            <time className="shrink-0" dateTime={item.updatedAt}>{formattedTime}</time>
                            <span aria-hidden="true">·</span>
                            <span className="truncate">{t('conversation.eventCount', { count: String(item.eventCount) })}</span>
                          </div>
                        </button>
                        <button
                          type="button"
                          className="absolute right-1.5 top-1.5 rounded p-1 text-ops-muted opacity-0 transition-all duration-200 hover:bg-ops-danger/10 hover:text-ops-danger group-hover:opacity-100 focus:opacity-100 active:scale-95"
                          onClick={(event) => {
                            event.stopPropagation()
                            onDelete(item.id)
                          }}
                          aria-label={t('conversation.deleteTask', { title: displayTitle })}
                        >
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12" /></svg>
                        </button>
                      </li>
                    )
                  })}
                </ul>
              </section>
            )
          })
        ) : (
          <div className="flex h-full items-center justify-center px-5 text-center">
            <div className="max-w-[190px]">
              <div className="mx-auto mb-3 flex h-8 w-8 items-center justify-center rounded-md border border-ops-border/35 text-ops-muted" aria-hidden="true">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M6 3h9l3 3v15H6z" /><path d="M9 12h6" /></svg>
              </div>
              <div className="text-xs font-semibold text-ops-text">{t('conversation.noTasks')}</div>
              <div className="mt-1.5 text-[10px] leading-5 text-ops-muted/70">{t('conversation.noTasksDescription')}</div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
