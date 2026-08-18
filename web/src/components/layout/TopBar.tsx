import { NotificationCenter } from './NotificationCenter'

type TopBarProps = {
  assets?: Array<{ id: number; name: string }>
  selectedAsset?: { name: string; host: string } | null
  onSelectConversation?: (conversationId: string) => void
  onSelectAsset?: (assetId: number) => void
}

export function TopBar({
  assets = [],
  selectedAsset,
  onSelectConversation = () => {},
  onSelectAsset = () => {},
}: TopBarProps) {
  return (
    <header className="desktop-title-bar" data-tauri-drag-region>
      <div className="flex min-w-0 items-center gap-2 text-[11px]" data-tauri-drag-region>
        <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-ops-green" />
        <span className="shrink-0 font-semibold text-ops-text">{selectedAsset?.host || selectedAsset?.name || '本地工作区'}</span>
        <span className="hidden text-ops-border sm:inline">/</span>
        <span className="hidden font-medium text-ops-muted/60 sm:inline">运维工作台</span>
      </div>
      <div className="flex items-center gap-1" aria-label="系统控制">
        <NotificationCenter
          assets={assets}
          onSelectConversation={onSelectConversation}
          onSelectAsset={onSelectAsset}
        />
      </div>
    </header>
  )
}
