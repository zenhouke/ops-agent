import type { AssetPayload } from '../../api'
import type { Asset, AssetGroup, ConversationSummary } from '../../types/ops'
import { ConversationList } from '../assistant/ConversationList'
import { AssetList } from './AssetList'
import { useAppearance } from '../../hooks/useAppearance'
import type { WorkspaceSection } from '../layout/ActivityRail'

type ConversationRunBadge = {
  conversationId: string
  status: 'running' | 'needs_approval' | 'completed' | 'failed'
  hasUnread: boolean
}

type AssetSidebarProps = {
  assets: Asset[]
  groups: AssetGroup[]
  conversationSummaries: ConversationSummary[]
  activeConversationId: string | null
  backgroundRun: ConversationRunBadge | null
  selectedAssetId: number
  collapsed: boolean
  activeSection: WorkspaceSection
  onToggleCollapse: () => void
  onSelectAsset: (assetId: number) => void
  onSelectConversation: (conversationId: string) => void
  onDeleteConversation: (conversationId: string) => void
  onUpdateAsset: (assetId: number, payload: AssetPayload) => Promise<Asset>
  onDeleteAsset: (assetId: number) => Promise<void>
  onAddAsset: () => void
  onManageGroups: () => void
  onEditAsset?: (asset: Asset) => void
  onDeleteAssetConfirm?: (asset: Asset) => void
}

export function AssetSidebar({ assets, groups, conversationSummaries, activeConversationId, backgroundRun, selectedAssetId, collapsed, activeSection, onToggleCollapse, onSelectAsset, onSelectConversation, onDeleteConversation, onUpdateAsset, onDeleteAsset, onAddAsset, onManageGroups, onEditAsset, onDeleteAssetConfirm }: AssetSidebarProps) {
  const { t } = useAppearance()

  return (
    <aside className={`h-full overflow-hidden border-r bg-ops-panel/70 transition-[width,border-color] duration-200 ease-out ${collapsed ? 'w-0 border-transparent' : 'w-[248px] border-ops-border/35'}`} aria-label="Resource explorer">
      <div className="flex h-full min-w-[248px] flex-col">
        <div className="flex h-10 items-center justify-between border-b border-ops-border/25 bg-ops-deep/55 px-3">
          <div className="flex min-w-0 items-center gap-2">
            <h2 className="truncate text-[11px] font-semibold text-ops-text">
              {activeSection === 'assets' ? t('assets.nodes') : t('conversation.taskHistory')}
            </h2>
            {activeSection === 'conversations' && conversationSummaries.length > 0 ? (
              <span className="rounded border border-ops-border/30 px-1.5 py-0.5 text-[9px] leading-none text-ops-muted/70">
                {conversationSummaries.length}
              </span>
            ) : null}
          </div>
          <div className="flex items-center gap-1">
            {activeSection === 'assets' ? (
              <>
                <button type="button" className="desktop-icon-button" aria-label={t('management.manageGroups')} title={t('management.manageGroups')} onClick={onManageGroups}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h7l2 2h9v10H3z" /><path d="M12 12v4M10 14h4" /></svg>
                </button>
                <button type="button" className="desktop-icon-button" aria-label={t('assets.addNodeConnection')} onClick={onAddAsset}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
                </button>
              </>
            ) : null}
            <button type="button" className="desktop-icon-button" aria-label={t('assets.collapseNavigation')} onClick={onToggleCollapse}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M15 18l-6-6 6-6" /></svg>
            </button>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-hidden">
          {activeSection === 'assets' ? (
          <div className="h-full overflow-y-auto overflow-x-hidden">
            <AssetList
              assets={assets}
              groups={groups}
              selectedAssetId={selectedAssetId}
              onSelectAsset={onSelectAsset}
              onAddAsset={onAddAsset}
              onUpdateAsset={onUpdateAsset}
              onDeleteAsset={onDeleteAsset}
              onEditAsset={onEditAsset}
              onDeleteAssetConfirm={onDeleteAssetConfirm}
            />
          </div>
          ) : (
          <div className="h-full overflow-hidden">
            <ConversationList
              items={conversationSummaries}
              activeConversationId={activeConversationId}
              backgroundRun={backgroundRun}
              onSelect={onSelectConversation}
              onDelete={onDeleteConversation}
            />
          </div>
          )}
        </div>
      </div>
    </aside>
  )
}
