import type { Asset } from '../../types/ops'
import { TerminalHeader } from './TerminalHeader'
import { TerminalOutput } from './TerminalOutput'

type TerminalPanelProps = {
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
  return (
    <section className="flex h-full w-full flex-col overflow-hidden bg-black shadow-inner" aria-label="终端面板">
      <TerminalHeader
        tabs={tabs}
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
      <TerminalOutput sessionKey={String(activeAssetId)} output={output} onInput={onInput} onResize={onResize} />
    </section>
  )
}
