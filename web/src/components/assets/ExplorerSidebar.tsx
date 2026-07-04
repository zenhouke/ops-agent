import { useState } from 'react'
import { type AssetPayload } from '../../api'
import type { Asset, AssetGroup } from '../../types/ops'
import { useAppearance } from '../../hooks/useAppearance'

type ExplorerSidebarProps = {
  open: boolean
  onClose: () => void
  assets: Asset[]
  groups: AssetGroup[]
  selectedAssetId: number
  onSelectAsset: (assetId: number) => void
  onUpdateAsset: (assetId: number, payload: AssetPayload) => Promise<Asset>
  onDeleteAsset: (assetId: number) => Promise<void>
  onAddAsset: () => void
  onEditAsset?: (asset: Asset) => void
  onDeleteAssetConfirm?: (asset: Asset) => void
}

export function ExplorerSidebar({
  open,
  onClose,
  assets,
  groups,
  selectedAssetId,
  onSelectAsset,
  onAddAsset,
  onEditAsset,
  onDeleteAssetConfirm,
}: ExplorerSidebarProps) {
  const { t } = useAppearance()
  const [expandedGroups, setExpandedGroups] = useState<Record<number, boolean>>({})
  const [searchQuery, setSearchQuery] = useState('')

  const toggleGroup = (groupId: number) => {
    setExpandedGroups((prev: Record<number, boolean>) => ({ ...prev, [groupId]: !prev[groupId] }))
  }

  const ungroupedAssets = assets.filter((asset) => asset.groupId === null)

  const groupSections = groups.map((group) => ({
    group,
    assets: assets.filter((asset) => asset.groupId === group.id),
  })).filter((section) => section.assets.length > 0)

  const filterAssets = (list: Asset[]) => {
    if (!searchQuery.trim()) return list
    const q = searchQuery.toLowerCase()
    return list.filter(
      (a) => a.name.toLowerCase().includes(q) || (a.host && a.host.toLowerCase().includes(q))
    )
  }

  const allFiltered = groupSections
    .map((s) => ({ ...s, assets: filterAssets(s.assets) }))
    .filter((s) => s.assets.length > 0)
  const filteredUngrouped = filterAssets(ungroupedAssets)

  const handleSelectAsset = (assetId: number) => {
    onSelectAsset(assetId)
    onClose()
  }

  return (
    <>
      {/* Backdrop */}
      {open ? (
        <div
          className="fixed left-0 right-0 top-12 bottom-0 z-40 bg-black/50 backdrop-blur-sm transition-opacity duration-200"
          onClick={onClose}
          aria-hidden="true"
        />
      ) : null}

      {/* Drawer */}
      <div
        className={`fixed left-0 top-12 bottom-0 z-50 flex w-[280px] flex-col border-r border-ops-border/30 bg-gradient-to-b from-ops-panel to-ops-panel/80 shadow-2xl transition-transform duration-300 ease-out ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Header */}
        <div className="flex h-12 shrink-0 items-center gap-2 border-b border-ops-border/15 bg-ops-bg/30 px-4">
          <div className="h-2 w-2 rounded-full bg-ops-green/60 shadow-[0_0_6px_rgb(var(--ops-green)/0.35)]" />
          <h2 className="flex-1 text-[11px] font-black tracking-[0.14em] text-ops-muted/60">{t('assets.navigationTitle')}</h2>
          <button
            type="button"
            onClick={onAddAsset}
            className="flex h-7 w-7 items-center justify-center rounded-lg text-ops-muted/50 transition-all duration-200 hover:bg-ops-green/12 hover:text-ops-green active:scale-90"
            aria-label={t('assets.addNodeConnection')}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
          </button>
          <button
            type="button"
            onClick={onClose}
            className="flex h-7 w-7 items-center justify-center rounded-lg text-ops-muted/50 transition-all duration-200 hover:bg-ops-danger/12 hover:text-ops-danger active:scale-90"
            aria-label={t('assets.collapseNavigation')}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M18 6 6 18M6 6l12 12" /></svg>
          </button>
        </div>

        {/* Search */}
        <div className="shrink-0 px-3 py-2">
          <div className="flex items-center gap-2 rounded-lg border border-ops-border/15 bg-ops-deep/60 px-2.5 py-1.5 text-[11px] text-ops-muted/50 transition-all focus-within:border-ops-green/30 focus-within:bg-ops-deep/80">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" /></svg>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t('assets.searchTargets')}
              className="min-w-0 flex-1 bg-transparent outline-none text-ops-text/70 placeholder:text-ops-muted/30"
            />
            {searchQuery ? (
              <button type="button" onClick={() => setSearchQuery('')} className="text-ops-muted/30 hover:text-ops-muted/60">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round"><path d="M18 6 6 18M6 6l12 12" /></svg>
              </button>
            ) : null}
          </div>
        </div>

        {/* Assets section */}
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="shrink-0 px-4 py-1.5">
            <span className="text-[9px] font-black uppercase tracking-[0.18em] text-ops-muted/35">{t('assets.nodeAssets')}</span>
          </div>
          <div className="flex-1 overflow-y-auto overflow-x-hidden px-2.5 pb-2 space-y-0.5">
            {groupSections.map(({ group, assets: groupAssets }) => {
              const isExpanded = expandedGroups[group.id] !== false
              const filtered = filterAssets(groupAssets)
              if (searchQuery && filtered.length === 0) return null
              return (
                <div key={group.id} className="mb-1">
                  <button
                    type="button"
                    onClick={() => toggleGroup(group.id)}
                    className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-[10px] font-bold tracking-[0.08em] text-ops-muted/45 transition-colors hover:text-ops-muted/70"
                  >
                    <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round"
                      className={`transition-transform duration-150 ${isExpanded ? 'rotate-90' : ''}`}>
                      <path d="m9 18 6-6-6-6" />
                    </svg>
                    <span className="truncate">{group.name}</span>
                    <span className="ml-auto text-[9px] text-ops-muted/30">{groupAssets.length}</span>
                  </button>
                  {isExpanded ? (
                    <div className="ml-1 mt-0.5 space-y-0.5">
                      {filtered.map((asset) => (
                        <AssetRow
                          key={asset.id}
                          asset={asset}
                          selected={asset.id === selectedAssetId}
                          onSelect={() => handleSelectAsset(asset.id)}
                          onEdit={() => onEditAsset?.(asset)}
                          onDelete={() => onDeleteAssetConfirm?.(asset)}
                        />
                      ))}
                    </div>
                  ) : null}
                </div>
              )
            })}

            {filteredUngrouped.length > 0 ? (
              <div className="space-y-0.5">
                {groupSections.length > 0 ? (
                  <div className="px-2 py-1 text-[9px] font-black uppercase tracking-[0.14em] text-ops-muted/30">{t('assets.ungrouped')}</div>
                ) : null}
                {filteredUngrouped.map((asset) => (
                  <AssetRow
                    key={asset.id}
                    asset={asset}
                    selected={asset.id === selectedAssetId}
                    onSelect={() => handleSelectAsset(asset.id)}
                    onEdit={() => onEditAsset?.(asset)}
                    onDelete={() => onDeleteAssetConfirm?.(asset)}
                  />
                ))}
              </div>
            ) : null}

            {searchQuery && allFiltered.length === 0 && filteredUngrouped.length === 0 ? (
              <div className="px-3 py-6 text-center text-[11px] text-ops-muted/40">{t('assets.noMatchingTargets')}</div>
            ) : null}
          </div>
        </div>
      </div>
    </>
  )
}

function AssetRow({
  asset,
  selected,
  onSelect,
  onEdit,
  onDelete,
}: {
  asset: Asset
  selected: boolean
  onSelect: () => void
  onEdit?: () => void
  onDelete?: () => void
}) {
  const assetName = asset.name || asset.host || `Asset #${asset.id}`
  const ipOrHost = asset.host || ''
  const typeLabel = asset.assetType === 'local_terminal' ? 'local'
    : asset.assetType === 'linux' ? 'server'
      : asset.assetType === 'serial' ? 'serial'
        : asset.assetType

  return (
    <div
      className={`group relative flex cursor-pointer items-start gap-2.5 rounded-xl px-3 py-2.5 transition-all duration-200 ${
        selected
          ? 'bg-gradient-to-r from-ops-green/12 to-ops-green/5 border border-ops-green/20 shadow-[0_0_12px_rgb(var(--ops-green)/0.08)]'
          : 'border border-transparent hover:border-ops-border/15 hover:bg-ops-panel/40'
      }`}
      onClick={onSelect}
    >
      <div className="flex flex-col items-center gap-1 pt-0.5">
        <span className={`h-2 w-2 rounded-full ${
          selected
            ? 'bg-ops-green shadow-[0_0_6px_rgb(var(--ops-green)/0.5)]'
            : 'bg-ops-border/30 group-hover:bg-ops-border/50'
        } transition-all duration-200`} />
      </div>

      <div className="min-w-0 flex-1">
        <div className={`flex items-center gap-2 text-[13px] font-bold leading-tight ${
          selected ? 'text-ops-text' : 'text-ops-text/80'
        }`}>
          <span className="truncate">{assetName}</span>
          <span className={`shrink-0 rounded-md px-1.5 py-0.5 text-[8px] font-black uppercase tracking-[0.1em] ${
            selected
              ? 'bg-ops-green/15 text-ops-green'
              : 'bg-ops-panel/50 text-ops-muted/35'
          }`}>
            {typeLabel}
          </span>
        </div>
        {ipOrHost ? (
          <div className="mt-0.5 truncate text-[11px] font-mono text-ops-muted/45">{ipOrHost}</div>
        ) : null}
      </div>

      <div className="flex shrink-0 items-center gap-0.5 pt-0.5 opacity-0 transition-all duration-200 group-hover:opacity-100">
        {onEdit ? (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onEdit() }}
            className="flex h-6 w-6 items-center justify-center rounded-lg text-ops-muted/30 transition-all hover:bg-ops-green/12 hover:text-ops-green active:scale-90"
          >
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" /></svg>
          </button>
        ) : null}
        {onDelete ? (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onDelete() }}
            className="flex h-6 w-6 items-center justify-center rounded-lg text-ops-muted/30 transition-all hover:bg-ops-danger/12 hover:text-ops-danger active:scale-90"
          >
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" /></svg>
          </button>
        ) : null}
      </div>
    </div>
  )
}
