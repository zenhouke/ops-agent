import type { Asset } from '../../types/ops'
import { useAppearance } from '../../hooks/useAppearance'
import { TerminalHeader } from './TerminalHeader'
import { TerminalOutput } from './TerminalOutput'

type TerminalPanelProps = {
  connectingAssetIds: number[]
  tabs: Asset[]
  activeAssetId: number
  output: string
  busyCommand: string | null
  onInput: (data: string) => void
  onResize: (cols: number, rows: number) => void
  onSelectTab: (assetId: number) => void
  onCloseTab: (assetId: number) => void
  onClear: () => void
  onCopy: () => void
  onReconnect: () => void
  focused: boolean
  onToggleFocus: () => void
  onClose: () => void
}

export function TerminalPanel({
  connectingAssetIds,
  tabs,
  activeAssetId,
  output,
  busyCommand,
  onInput,
  onResize,
  onSelectTab,
  onCloseTab,
  onClear,
  onCopy,
  onReconnect,
  focused,
  onToggleFocus,
  onClose,
}: TerminalPanelProps) {
  const { terminalBackground } = useAppearance()

  return (
    <section className="flex h-full w-full flex-col overflow-hidden shadow-inner" style={{ backgroundColor: terminalBackground }} aria-label="终端面板">
      <TerminalHeader
        tabs={tabs}
        connectingAssetIds={connectingAssetIds}
        activeAssetId={activeAssetId}
        busyCommand={busyCommand}
        onSelectTab={onSelectTab}
        onCloseTab={onCloseTab}
        onClear={onClear}
        onCopy={onCopy}
        onReconnect={onReconnect}
        focused={focused}
        onToggleFocus={onToggleFocus}
        onClose={onClose}
      />
      {connectingAssetIds.includes(activeAssetId) ? (
        <div role="status" aria-live="polite" className="flex items-center gap-2 border-b border-ops-border/30 px-3 py-2 text-xs text-ops-muted">
          <span aria-hidden="true" className="h-3 w-3 animate-spin rounded-full border-2 border-ops-muted/30 border-t-ops-cyan" />
          正在连接 {tabs.find((asset) => asset.id === activeAssetId)?.name}，请稍候…
        </div>
      ) : null}
      <TerminalOutput sessionKey={String(activeAssetId)} output={output} onInput={onInput} onResize={onResize} />
    </section>
  )
}
