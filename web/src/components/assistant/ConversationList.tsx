import { useAppearance } from '../../hooks/useAppearance'
import type { ConversationSummary, EventItem } from '../../types/ops'
import { formatDateTime } from '../../utils/dateTime'

export type ConversationRunBadge = {
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

const timeFormatter = new Intl.DateTimeFormat('en-US', {
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
})

type EventKind = EventItem['kind']
type KnownEventKind = EventKind | 'approval' | 'output' | 'status'

const KNOWN_EVENT_KIND_SET: ReadonlySet<KnownEventKind> = new Set<KnownEventKind>([
  'delta', 'plan', 'approval_required', 'approval_decision',
  'command_start', 'command_chunk', 'command_end', 'terminal_status',
  'final', 'error', 'user', 'approval', 'output', 'status',
])

function normalizeStatusKind(kind: string | null): KnownEventKind | null {
  if (!kind) return null
  return KNOWN_EVENT_KIND_SET.has(kind as KnownEventKind) ? (kind as KnownEventKind) : null
}

function getStatusDot(kind: KnownEventKind | null): string {
  switch (kind) {
    case 'approval_required': return 'bg-ops-warning'
    case 'approval_decision': return 'bg-ops-green'
    case 'error': return 'bg-ops-danger'
    case 'final': return 'bg-ops-emerald'
    case 'plan':
    case 'delta':
    case 'status':
    case 'command_start':
    case 'command_chunk': return 'bg-ops-green'
    case 'command_end':
    case 'terminal_status':
    case 'user':
    case 'output': return 'bg-ops-border/40'
    default: return 'bg-ops-border/20'
  }
}

function getRunBadgeMeta(run: ConversationRunBadge | null) {
  if (!run) return null
  if (run.status === 'needs_approval') return { label: '需审批', dot: 'bg-ops-warning' }
  if (run.status === 'completed') return { label: run.hasUnread ? '完成 · 新' : '完成', dot: 'bg-ops-emerald' }
  if (run.status === 'failed') return { label: '失败', dot: 'bg-ops-danger' }
  return { label: run.hasUnread ? '运行中 · 新' : '运行中', dot: 'bg-ops-green' }
}

export function ConversationList({ items, activeConversationId, backgroundRun, onSelect, onDelete }: ConversationListProps) {
  const { t } = useAppearance()

  return (
    <div className="flex h-full flex-col" aria-label={t('conversation.list')}>
      <div className="flex-1 overflow-y-auto px-1.5 py-1">
        {items.length > 0 ? (
          <ul className="flex flex-col gap-px" role="list">
            {items.map((item) => {
              const isActive = item.id === activeConversationId
              const status = getStatusDot(normalizeStatusKind(item.lastEventKind))
              const isUntitled = !item.title || item.title.trim() === '' || item.title.trim() === 'New'
              const displayTitle = isUntitled ? t('conversation.untitledSession') : item.title
              const runBadge = getRunBadgeMeta(backgroundRun?.conversationId === item.id ? backgroundRun : null)

              return (
                <li key={item.id} className="group relative">
                  <button
                    type="button"
                    className={`relative flex w-full items-center gap-2.5 rounded-lg px-3 py-2 pr-9 text-left transition-all duration-200 active:scale-[0.98] ${isActive
                      ? 'bg-ops-green/10 text-ops-green'
                      : 'text-ops-muted hover:bg-ops-panel/40 hover:text-ops-text'
                      }`}
                    onClick={() => onSelect(item.id)}
                    title={displayTitle}
                  >
                    {/* Active indicator */}
                    {isActive ? (
                      <span className="absolute left-0 top-1/2 h-4 w-[3px] -translate-y-1/2 rounded-r-full bg-ops-green shadow-glow" aria-hidden="true" />
                    ) : null}

                    {/* Status dot */}
                    <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${isActive ? status : 'bg-ops-border/20'} ${runBadge?.dot ? 'animate-pulse' : ''}`} />

                    {/* Title + meta */}
                    <div className="min-w-0 flex-1">
                      <div className={`flex items-center gap-2 text-[12px] font-bold leading-tight ${isActive ? 'text-ops-text' : 'text-ops-text/75'}`}>
                        <span className={`truncate ${isUntitled ? 'italic text-ops-muted/50' : ''}`}>{displayTitle}</span>
                        {runBadge ? (
                          <span className={`shrink-0 h-1.5 w-1.5 rounded-full ${runBadge.dot} animate-pulse`} />
                        ) : null}
                      </div>
                      <div className="mt-0.5 text-[10px] font-medium text-ops-muted/40">
                        {formatDateTime(item.updatedAt, timeFormatter, item.updatedAt)}
                      </div>
                    </div>
                  </button>

                  {/* Delete button */}
                  <button
                    type="button"
                    className="absolute right-2 top-1/2 flex h-5 w-5 -translate-y-1/2 items-center justify-center rounded text-ops-muted/30 opacity-0 transition-all duration-200 hover:bg-ops-danger/15 hover:text-ops-danger group-hover:opacity-100 active:scale-90"
                    onClick={(e) => { e.stopPropagation(); onDelete(item.id) }}
                    aria-label={t('conversation.deleteSession', { title: displayTitle })}
                  >
                    <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
                  </button>
                </li>
              )
            })}
          </ul>
        ) : (
          <div className="px-3 py-4 text-[11px] text-ops-muted/50">
            <span className="font-bold">{t('conversation.noSessions')}</span>
          </div>
        )}
      </div>
    </div>
  )
}
