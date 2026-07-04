import { useAppearance } from '../../hooks/useAppearance'
import type { Asset } from '../../types/ops'
import { LOCAL_TERMINAL_ASSET_ID } from '../../hooks/console/consoleShared'

type TerminalHeaderProps = {
  asset: Asset
  tabs: Asset[]
  activeAssetId: number
  busyCommand: string | null
  onSelectTab: (assetId: number) => void
  onCloseTab: (assetId: number) => void
  onClear: () => void
  onCopy: () => void
  onReconnect: () => void
}

export function TerminalHeader({
  asset,
  tabs,
  activeAssetId,
  busyCommand,
  onSelectTab,
  onCloseTab,
  onClear,
  onCopy,
  onReconnect,
}: TerminalHeaderProps) {
  const { t } = useAppearance()

  return (
    <header className="flex h-[60px] shrink-0 flex-col border-b border-ops-border/15 bg-ops-deep relative overflow-hidden dark:border-ops-border/20 dark:bg-ops-panel/80">
      <div className="absolute top- left-0 w-1 h-full bg-ops-green/20 pointer-events-none" />
      <div className="flex items-center gap-3 px-3 py-2">
        {/* Tabs (with close button, local terminal is permanent) */}
        <div className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto" aria-label={t('terminal.tabs')}>
          {tabs.map((tabAsset) => {
            const isActive = tabAsset.id === activeAssetId
            const isLocal = tabAsset.id === LOCAL_TERMINAL_ASSET_ID
            const label = tabAsset.name || tabAsset.host || t('terminal.terminal')
            return (
              <div
                key={tabAsset.id}
                className={`group relative flex max-w-[200px] shrink-0 items-center rounded-xl border transition-all duration-300 ${isActive
                  ? 'border-ops-green/30 bg-ops-green/10 shadow-glow'
                  : 'border-transparent bg-transparent hover:border-ops-border/20 hover:bg-ops-panel/40'
                  }`}
              >
                <button
                  type="button"
                  className={`flex min-w-0 items-center gap-2.5 px-4 py-2 text-[10px] font-bold tracking-[0.1em] ${isActive ? 'text-ops-green shadow-glow' : 'text-ops-muted/60'
                    }`}
                  onClick={() => onSelectTab(tabAsset.id)}
                  title={`${label}${isLocal ? ` (${t('terminal.local')})` : ''}`}
                >
                  <span
                    className={`h-1.5 w-1.5 shrink-0 rounded-full ${isActive ? 'bg-ops-green shadow-glow' : 'bg-ops-border/40'}`}
                    aria-hidden="true"
                  />
                  <span className="truncate">{label}</span>
                </button>
                {isLocal ? null : (
                  <button
                    type="button"
                    className="mr-1.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-ops-muted opacity-0 transition-all duration-200 hover:bg-ops-danger/20 hover:text-ops-danger group-hover:opacity-100 focus:opacity-100 active:scale-95"
                    onClick={(event) => {
                      event.stopPropagation()
                      onCloseTab(tabAsset.id)
                    }}
                    aria-label={t('terminal.closeTerminal', { label })}
                    title={t('terminal.close', { label })}
                  >
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
                  </button>
                )}
              </div>
            )
          })}
        </div>

        {/* Tool Button Group */}
        <div className="flex shrink-0 items-center gap-1 rounded-xl border border-ops-border/20 bg-ops-panel/60 p-1 shadow-sm">
          <ToolButton onClick={onClear} title={t('terminal.clearScreen')} aria-label={t('terminal.clearTerminal')}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" /></svg>
          </ToolButton>
          <ToolButton onClick={onCopy} title={t('terminal.copyBuffer')} aria-label={t('terminal.copyOutput')}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" /></svg>
          </ToolButton>
          <ToolButton onClick={onReconnect} title={t('terminal.resetSocket')} aria-label={t('terminal.reconnectSession')}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12a9 9 0 11-3-6.7M21 4v5h-5" /></svg>
          </ToolButton>
        </div>
      </div>

      {busyCommand ? (
        <div className="flex items-center gap-4 border-t border-ops-warning/30 bg-ops-warning/5 px-5 py-2 text-[10px] text-ops-warning animate-in slide-in-from-top duration-300">
          <div className="flex items-center gap-2 shrink-0">
            <span className="h-2 w-2 rounded-full bg-ops-warning shadow-glow" />
            <span className="font-bold tracking-[0.1em]">{t('terminal.transmissionInProgress')}</span>
          </div>
          <code className="min-w-0 flex-1 truncate font-mono text-[11px] text-ops-text/80 bg-ops-warning/10 px-2 py-0.5 rounded border border-ops-warning/20" title={busyCommand}>
            {busyCommand}
          </code>
        </div>
      ) : null}
    </header>
  )
}

type ToolButtonProps = {
  onClick: () => void
  title: string
  'aria-label': string
  children: React.ReactNode
}

function ToolButton({ onClick, title, 'aria-label': ariaLabel, children }: ToolButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      aria-label={ariaLabel}
      className="flex h-7 w-7 items-center justify-center rounded-md text-ops-muted transition-all duration-200 hover:bg-ops-border/30 hover:text-ops-green active:scale-95"
    >
      {children}
    </button>
  )
}
