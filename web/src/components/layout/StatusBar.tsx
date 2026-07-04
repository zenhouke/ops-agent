import { useAppearance } from '../../hooks/useAppearance'
import type { Asset } from '../../types/ops'
import type { ConversationRunBadge } from '../assistant/ConversationList'

type StatusBarProps = {
  selectedAsset: Asset | null
  terminalOpen: boolean
  terminalCount: number
  busyCommand: string | null
  backgroundRun: ConversationRunBadge | null
  selectedModel: string | null
  terminalConnected?: boolean
}

export function StatusBar({
  selectedAsset,
  terminalOpen,
  terminalCount,
  busyCommand,
  backgroundRun,
  selectedModel,
  terminalConnected,
}: StatusBarProps) {
  const { t } = useAppearance()

  const statusDots: Array<{
    label: string
    dotColor: string
  }> = []

  // Asset status
  if (selectedAsset) {
    statusDots.push({
      label: selectedAsset.name,
      dotColor: 'bg-ops-green',
    })
  }

  // Terminal connection
  if (terminalCount > 0) {
    statusDots.push({
      label: terminalConnected !== false
        ? t('StatusBar.terminalConnected')
        : t('StatusBar.terminalDisconnected'),
      dotColor: terminalConnected !== false ? 'bg-ops-emerald' : 'bg-ops-danger',
    })
  }

  // Background run
  if (backgroundRun) {
    const dotColor = backgroundRun.status === 'needs_approval'
      ? 'bg-ops-warning'
      : backgroundRun.status === 'running'
        ? 'bg-ops-green'
        : backgroundRun.status === 'failed'
          ? 'bg-ops-danger'
          : 'bg-ops-emerald'
    statusDots.push({
      label: backgroundRun.status === 'needs_approval'
        ? t('StatusBar.awaitingApproval')
        : backgroundRun.status === 'running'
          ? t('StatusBar.runInProgress')
          : t('StatusBar.runComplete'),
      dotColor,
    })
  }

  // Busy command
  if (busyCommand) {
    statusDots.push({
      label: t('StatusBar.operationInProgress'),
      dotColor: 'bg-ops-warning',
    })
  }

  // Model
  if (selectedModel) {
    statusDots.push({
      label: selectedModel,
      dotColor: 'bg-ops-muted',
    })
  }

  return (
    <footer className="flex h-7 shrink-0 items-center justify-between border-t border-ops-border/15 bg-ops-deep px-3">
      <div className="flex items-center gap-3 overflow-x-auto">
        {statusDots.length > 0 ? (
          statusDots.map((item, index) => (
            <div key={index} className="flex items-center gap-1.5 shrink-0">
              <span className={`h-1.5 w-1.5 rounded-full ${item.dotColor}`} />
              <span className="text-[10px] font-semibold text-ops-muted/70 truncate max-w-[160px]">{item.label}</span>
            </div>
          ))
        ) : (
          <span className="text-[10px] font-semibold text-ops-muted/40">{t('StatusBar.ready')}</span>
        )}
      </div>
      <span className="shrink-0 text-[10px] font-semibold text-ops-muted/40">
        {terminalOpen ? t('StatusBar.terminalOpen', { count: String(terminalCount) }) : terminalCount > 0 ? t('StatusBar.terminalTabs', { count: String(terminalCount) }) : null}
      </span>
    </footer>
  )
}