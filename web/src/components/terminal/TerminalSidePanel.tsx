import { useCallback, useRef, useState } from 'react'
import type { Asset } from '../../types/ops'
import { useAppearance } from '../../hooks/useAppearance'
import { TerminalOutput } from './TerminalOutput'
import { LOCAL_TERMINAL_ASSET_ID } from '../../hooks/console/consoleShared'

type TerminalSidePanelProps = {
  open: boolean
  onClose: () => void
  terminalTabs: Array<{ asset: Asset; output: string }>
  activeAssetId: number
  busyCommand: string | null
  onSelectTab: (assetId: number) => void
  onCloseTab: (assetId: number) => void
  onInput: (data: string) => void
  onResize: (cols: number, rows: number) => void
  onClear: () => void
  onCopy: () => void
  onReconnect: () => void
}

const PANEL_MIN_WIDTH = 320
const PANEL_DEFAULT_WIDTH = 440
const PANEL_MAX_WIDTH = 720

export function TerminalSidePanel({
  open,
  onClose,
  terminalTabs,
  activeAssetId,
  busyCommand,
  onSelectTab,
  onCloseTab,
  onInput,
  onResize,
  onClear,
  onCopy,
  onReconnect,
}: TerminalSidePanelProps) {
  const { t } = useAppearance()
  const [panelWidth, setPanelWidth] = useState(PANEL_DEFAULT_WIDTH)
  const dragRef = useRef<{ startX: number; startWidth: number } | null>(null)

  const hasTabs = terminalTabs.length > 0

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    dragRef.current = { startX: e.clientX, startWidth: panelWidth }

    const handleMouseMove = (ev: MouseEvent) => {
      if (!dragRef.current) return
      const delta = dragRef.current.startX - ev.clientX
      const newWidth = Math.min(PANEL_MAX_WIDTH, Math.max(PANEL_MIN_WIDTH, dragRef.current.startWidth + delta))
      setPanelWidth(newWidth)
    }

    const handleMouseUp = () => {
      dragRef.current = null
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
  }, [panelWidth])

  const activeTab = terminalTabs.find((item) => item.asset.id === activeAssetId)
  const output = activeTab?.output ?? ''

  return (
    <>
      {/* Backdrop */}
      {open && hasTabs ? (
        <div
          className="fixed left-0 right-0 top-12 bottom-0 z-40 bg-black/50 backdrop-blur-sm transition-opacity duration-200"
          onClick={onClose}
          aria-hidden="true"
        />
      ) : null}

      {/* Drawer */}
      <div
        className={`fixed right-0 top-12 bottom-0 z-50 flex shrink-0 border-l border-ops-border/30 bg-gradient-to-b from-ops-panel to-ops-deep shadow-2xl transition-transform duration-300 ease-out ${
          open && hasTabs ? 'translate-x-0' : 'translate-x-full'
        }`}
        style={{ width: `${panelWidth}px` }}
      >
        {/* Drag handle */}
        <div
          className="absolute left-0 top-0 z-20 h-full w-1.5 cursor-col-resize group"
          onMouseDown={handleMouseDown}
        >
          <div className="mx-auto h-full w-px bg-ops-border/10 transition-colors group-hover:bg-ops-green/40" />
        </div>

        <div className="flex h-full min-h-0 w-full flex-col">
          {/* Header */}
          <div className="flex h-12 shrink-0 items-center justify-between border-b border-ops-border/15 bg-ops-panel/60 px-3">
            <div className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-ops-green" />
              <span className="text-[10px] font-black uppercase tracking-[0.14em] text-ops-muted/60">{t('terminal.terminal')}</span>
            </div>
            <div className="flex items-center gap-1">
              <ToolButton onClick={onClear} title={t('terminal.clearScreen')}>
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" /></svg>
              </ToolButton>
              <ToolButton onClick={onCopy} title={t('terminal.copyBuffer')}>
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" /></svg>
              </ToolButton>
              <ToolButton onClick={onReconnect} title={t('terminal.resetSocket')}>
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M21 12a9 9 0 11-3-6.7M21 4v5h-5" /></svg>
              </ToolButton>
              <button
                type="button"
                onClick={onClose}
                className="flex h-6 w-6 items-center justify-center rounded text-ops-muted/50 transition-all duration-200 hover:bg-ops-danger/20 hover:text-ops-danger active:scale-90"
                aria-label={t('terminal.collapse')}
              >
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M18 6 6 18M6 6l12 12" /></svg>
              </button>
            </div>
          </div>

          {/* Tab strip */}
          <div className="flex shrink-0 items-center gap-1 overflow-x-auto border-b border-ops-border/10 bg-ops-panel/30 px-2 py-1" aria-label={t('terminal.tabs')}>
            {terminalTabs.map(({ asset: tabAsset }) => {
              const isActive = tabAsset.id === activeAssetId
              const isLocal = tabAsset.id === LOCAL_TERMINAL_ASSET_ID
              const label = tabAsset.name || tabAsset.host || t('terminal.terminal')
              return (
                <div
                  key={tabAsset.id}
                  className={`group relative flex max-w-[160px] shrink-0 items-center rounded-lg border transition-all duration-200 ${isActive
                    ? 'border-ops-green/25 bg-ops-green/10'
                    : 'border-transparent hover:border-ops-border/20 hover:bg-ops-panel/40'
                    }`}
                >
                  <button
                    type="button"
                    className={`flex min-w-0 items-center gap-2 px-2.5 py-1.5 text-[10px] font-bold tracking-[0.08em] ${isActive ? 'text-ops-green' : 'text-ops-muted/60'}`}
                    onClick={() => onSelectTab(tabAsset.id)}
                    title={`${label}${isLocal ? ` (${t('terminal.local')})` : ''}`}
                  >
                    <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${isActive ? 'bg-ops-green' : 'bg-ops-border/40'}`} aria-hidden="true" />
                    <span className="truncate">{label}</span>
                  </button>
                  {isLocal ? null : (
                    <button
                      type="button"
                      className="mr-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded text-ops-muted opacity-0 transition-all duration-200 hover:bg-ops-danger/20 hover:text-ops-danger group-hover:opacity-100 active:scale-90"
                      onClick={(e) => { e.stopPropagation(); onCloseTab(tabAsset.id) }}
                      aria-label={t('terminal.closeTerminal', { label })}
                    >
                      <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
                    </button>
                  )}
                </div>
              )
            })}
          </div>

          {/* Busy command indicator */}
          {busyCommand ? (
            <div className="flex shrink-0 items-center gap-2 border-b border-ops-warning/20 bg-ops-warning/5 px-3 py-1.5 text-[10px] text-ops-warning">
              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-ops-warning" />
              <code className="min-w-0 flex-1 truncate font-mono text-[10px]">{busyCommand}</code>
            </div>
          ) : null}

          {/* Terminal output — fills remaining height */}
          <div className="flex min-h-0 flex-1 overflow-hidden">
            <TerminalOutput
              sessionKey={String(activeAssetId)}
              output={output}
              onInput={onInput}
              onResize={onResize}
            />
          </div>
        </div>
      </div>
    </>
  )
}

function ToolButton({ onClick, title, children }: {
  onClick: () => void
  title: string
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className="flex h-6 w-6 items-center justify-center rounded text-ops-muted/50 transition-all duration-200 hover:bg-ops-border/30 hover:text-ops-green active:scale-90"
    >
      {children}
    </button>
  )
}
