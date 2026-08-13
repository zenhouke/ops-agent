import { useState } from 'react'
import { ListItemCard } from '../layout/ListItemCard'
import type { Asset, AssetGroup } from '../../types/ops'
import { useAppearance } from '../../hooks/useAppearance'

type AssetListProps = {
  assets: Asset[]
  groups: AssetGroup[]
  selectedAssetId: number
  onSelectAsset: (assetId: number) => void
  onUpdateAsset?: (assetId: number, payload: any) => Promise<any>
  onDeleteAsset?: (assetId: number) => Promise<void>
  onEditAsset?: (asset: Asset) => void
  onDeleteAssetConfirm?: (asset: Asset) => void
}

type AssetListGroup = {
  id: number | null
  label: string
}

function getAssetMeta(asset: Asset, localSystemLabel: string): string {
  return asset.assetType === 'local_terminal' ? localSystemLabel : `${asset.host}:${asset.port}`
}

export function AssetList({ assets, groups, selectedAssetId, onSelectAsset, onEditAsset, onDeleteAssetConfirm }: AssetListProps) {
  const { t } = useAppearance()
  const [menuAssetId, setMenuAssetId] = useState<number | null>(null)
  const visibleAssets = assets.filter((asset) => asset.assetType !== 'local_terminal')

  const assetGroups: AssetListGroup[] = [
    ...groups.map((group) => ({ id: group.id, label: group.name })),
    { id: null, label: t('assets.unassigned') },
  ]

  const groupedAssets = visibleAssets.reduce<Record<string, Asset[]>>(
    (grouped, asset) => {
      const key = String(asset.groupId)
      grouped[key] = [...(grouped[key] ?? []), asset]
      return grouped
    },
    {},
  )

  return (
    <div className="flex h-full flex-col bg-ops-deep/50" aria-label={t('assets.hostConnectionList')} onMouseLeave={() => setMenuAssetId(null)}>
      {visibleAssets.length === 0 ? <p className="text-center py-10 text-ops-muted text-[11px]  tracking-widest font-medium opacity-50">{t('assets.emptyWorkspace')}</p> : null}
      {assetGroups.map((group) => {
        const groupKey = String(group.id)
        const groupAssets = groupedAssets[groupKey] ?? []
        if (groupAssets.length === 0) {
          return null
        }

        return (
          <section key={groupKey} className="mb-1" aria-label={group.label}>
            <h3 className="border-y border-ops-border/20 bg-ops-bg/35 px-3 py-1.5 text-[9px] font-bold tracking-[0.1em] text-ops-muted/65">{group.label}</h3>
            <ul className="flex flex-col list-none m-0 p-0">
              {groupAssets.map((asset) => {
                const selected = asset.id === selectedAssetId
                const menuOpen = asset.id === menuAssetId

                return (
                  <li key={asset.id} className="relative group">
                    <div className={`relative flex items-center transition-all duration-200 ${selected ? 'bg-ops-cyan/5 shadow-[inset_2px_0_0_0_rgb(var(--ops-cyan))]' : 'hover:bg-ops-panel/40'} ${menuOpen ? 'bg-ops-panel/80' : ''}`}>
                      <ListItemCard
                        title={asset.name}
                        meta={getAssetMeta(asset, t('assets.localSystem'))}
                        active={selected}
                        onClick={() => onSelectAsset(asset.id)}
                        onContextMenu={(event) => {
                          event.preventDefault()
                          setMenuAssetId(asset.id)
                        }}
                      />

                      <button
                        type="button"
                        className={`absolute right-2 rounded-[4px] p-1.5 transition-all duration-200 z-10 active:scale-90 ${menuOpen ? 'opacity-100 bg-ops-cyan/15 text-ops-cyan' : 'opacity-0 group-hover:opacity-100 text-ops-muted hover:text-ops-cyan hover:bg-ops-cyan/10'
                          }`}
                        aria-label={t('assets.operations', { name: asset.name })}
                        onClick={(event) => {
                          event.stopPropagation()
                          setMenuAssetId((current) => (current === asset.id ? null : asset.id))
                        }}
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                          <circle cx="12" cy="12" r="1"></circle>
                          <circle cx="12" cy="5" r="1"></circle>
                          <circle cx="12" cy="19" r="1"></circle>
                        </svg>
                      </button>
                    </div>

                    {menuOpen ? (
                      <div className="absolute right-2 top-8 z-20 w-40 overflow-hidden rounded-[5px] border border-ops-border/45 bg-ops-panel shadow-xl backdrop-blur-md animate-in fade-in zoom-in duration-200" role="menu" aria-label={t('assets.operations', { name: asset.name })}>
                        <button
                          type="button"
                          className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-[11px] font-bold tracking-wide text-ops-text transition-all duration-200 hover:bg-ops-cyan hover:text-ops-bg active:scale-95"
                          role="menuitem"
                          onClick={() => {
                            onEditAsset?.(asset)
                            setMenuAssetId(null)
                          }}
                        >
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
                          {t('assets.updateInfo')}
                        </button>
                        <button
                          type="button"
                          className="flex w-full items-center gap-2.5 border-t border-ops-border/20 px-3 py-2 text-left text-[11px] font-bold tracking-wide text-ops-danger transition-all duration-200 hover:bg-ops-danger hover:text-ops-deep active:scale-95"
                          role="menuitem"
                          onClick={() => {
                            onDeleteAssetConfirm?.(asset)
                            setMenuAssetId(null)
                          }}
                        >
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
                          {t('assets.deleteAsset')}
                        </button>
                      </div>
                    ) : null}
                  </li>
                )
              })}
            </ul>
          </section>
        )
      })}
    </div>
  )
}
