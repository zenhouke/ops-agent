import { useEffect, useRef, useState } from 'react'
import type { ConversationSummary } from '../../types/ops'
import { useAppearance } from '../../hooks/useAppearance'
import type { ConversationRunBadge } from './ConversationList'
import { ConversationList } from './ConversationList'

type ConversationHistoryDropdownProps = {
  items: ConversationSummary[]
  activeConversationId: string | null
  activeConversationTitle: string
  backgroundRun: ConversationRunBadge | null
  onSelect: (conversationId: string) => void
  onDelete: (conversationId: string) => void
  onCreate: () => void
}

export function ConversationHistoryDropdown({
  items,
  activeConversationId,
  activeConversationTitle,
  backgroundRun,
  onSelect,
  onDelete,
  onCreate,
}: ConversationHistoryDropdownProps) {
  const { t } = useAppearance()
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('keydown', handleEscape)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleEscape)
    }
  }, [open])

  const handleSelect = (conversationId: string) => {
    onSelect(conversationId)
    setOpen(false)
  }

  const handleDelete = (conversationId: string) => {
    onDelete(conversationId)
  }

  const handleCreate = () => {
    onCreate()
    setOpen(false)
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="group flex min-w-0 max-w-[280px] items-center gap-2 rounded-lg border border-ops-border/15 bg-ops-panel/40 px-3 py-1.5 transition-all duration-200 hover:border-ops-green/30 hover:bg-ops-green/8 active:scale-[0.98]"
        aria-expanded={open}
        aria-label={t('assistant.switchSession')}
      >
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="shrink-0 text-ops-muted/50 transition-colors group-hover:text-ops-green"
        >
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
        <span className="min-w-0 flex-1 truncate text-left text-[13px] font-bold text-ops-text">
          {activeConversationTitle || t('assistant.unclassifiedMission')}
        </span>
        <svg
          width="10"
          height="10"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={`shrink-0 text-ops-muted/40 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>

      {open ? (
        <div className="absolute left-0 top-[calc(100%+6px)] z-50 w-[320px] overflow-hidden rounded-2xl border border-ops-border/30 bg-ops-panel/95 shadow-2xl backdrop-blur-md">
          {/* Header */}
          <div className="flex h-10 shrink-0 items-center justify-between border-b border-ops-border/15 bg-ops-bg/40 px-3">
            <span className="text-[10px] font-black uppercase tracking-[0.14em] text-ops-muted/50">
              {t('assistant.conversationHistory')}
            </span>
            <button
              type="button"
              onClick={handleCreate}
              className="flex h-6 items-center gap-1 rounded-lg border border-ops-green/25 bg-ops-green/10 px-2 text-[9px] font-bold tracking-[0.08em] text-ops-green transition-all duration-200 hover:bg-ops-green/20 active:scale-95"
            >
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
              {t('assistant.newSession')}
            </button>
          </div>

          {/* List */}
          <div className="max-h-[360px] overflow-y-auto py-1">
            <ConversationList
              items={items}
              activeConversationId={activeConversationId}
              backgroundRun={backgroundRun}
              onSelect={handleSelect}
              onDelete={handleDelete}
            />
          </div>
        </div>
      ) : null}
    </div>
  )
}
