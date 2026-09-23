import { useEffect, useState } from 'react'
import { ListItemCard } from '../layout/ListItemCard'
import type { Asset, AssetGroup } from '../../types/ops'
import { useAppearance } from '../../hooks/useAppearance'

type AssetListProps = {
  organizationTree?: boolean
  connectingAssetIds?: number[]
  assets: Asset[]
  groups: AssetGroup[]
  selectedAssetId: number | null
  onSelectAsset: (assetId: number) => void
  onUpdateAsset?: (assetId: number, payload: any) => Promise<any>
  onDeleteAsset?: (assetId: number) => Promise<void>
  onEditAsset?: (asset: Asset) => void
  onDeleteAssetConfirm?: (asset: Asset) => void
}

type AssetListGroup = {
  id: number | null
  label: string
  instanceLabel?: string
}

function getAssetMeta(asset: Asset, localSystemLabel: string): string {
  if (asset.assetType === 'local_terminal') return localSystemLabel
  return `${asset.host}:${asset.port}${asset.authType === 'jumpserver' ? ' · JumpServer' : ''}`
}

export function AssetList({ organizationTree = false, connectingAssetIds = [], assets, groups, selectedAssetId, onSelectAsset, onEditAsset, onDeleteAssetConfirm }: AssetListProps) {
  const { t } = useAppearance()
  const [menuAssetId, setMenuAssetId] = useState<number | null>(null)
  const [expandedOrganizations, setExpandedOrganizations] = useState<Record<string, boolean>>({})
  const visibleAssets = assets.filter((asset) => asset.assetType !== 'local_terminal')
  const selectedGroupId = assets.find((asset) => asset.id === selectedAssetId)?.groupId

  useEffect(() => {
    if (organizationTree && selectedGroupId !== undefined) {
      setExpandedOrganizations((current) => ({ ...current, [String(selectedGroupId)]: true }))
    }
  }, [organizationTree, selectedAssetId, selectedGroupId])

  const assetGroups: AssetListGroup[] = [
    ...groups.map((group) => {
      const isOrganization = organizationTree && group.description.startsWith('ops-agent:jumpserver-instance:') && group.description.includes(':org:')
      const parts = group.name.split(' · ')
      return { id: group.id, label: isOrganization ? parts.slice(2).join(' · ') || group.name : group.name, instanceLabel: isOrganization ? parts.slice(0, 2).join(' · ') : undefined }
    }),
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
      {organizationTree && visibleAssets.length > 0 ? <div className="flex items-center justify-between px-3 py-2 text-[10px] text-ops-muted/70"><span>按组织浏览 · {visibleAssets.length} 台资产</span><button type="button" className="text-ops-cyan/80 hover:text-ops-cyan" onClick={() => setExpandedOrganizations({})}>全部收起</button></div> : null}
      {visibleAssets.length === 0 ? <p className="text-center py-10 text-ops-muted text-[11px]  tracking-widest font-medium opacity-50">{t('assets.emptyWorkspace')}</p> : null}
      {assetGroups.map((group) => {
        const groupKey = String(group.id)
        const groupAssets = groupedAssets[groupKey] ?? []
        if (groupAssets.length === 0) {
          return null
        }
        const expanded = !organizationTree || Boolean(expandedOrganizations[groupKey])

        return (
          <section key={groupKey} className="mb-1" aria-label={group.label}>
            {organizationTree ? <h3>
              <button type="button" aria-expanded={expanded} aria-controls={`organization-assets-${groupKey}`} title={group.instanceLabel ? `${group.instanceLabel} / ${group.label}` : group.label} className={`flex w-full items-center gap-2 border-y border-ops-border/20 px-3 py-3 text-left hover:bg-ops-panel/70 ${expanded ? 'bg-ops-cyan/5' : 'bg-ops-bg/35'}`} onClick={() => setExpandedOrganizations((current) => ({ ...current, [groupKey]: !expanded }))}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={`shrink-0 text-ops-muted transition-transform ${expanded ? 'rotate-90' : ''}`} aria-hidden="true"><path d="m9 5 7 7-7 7" /></svg>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" className="shrink-0 text-ops-cyan/80" aria-hidden="true"><rect x="8" y="2" width="8" height="6" rx="1" /><path d="M12 8v5M4 16v-3h16v3" /><rect x="1" y="16" width="6" height="6" rx="1" /><rect x="9" y="16" width="6" height="6" rx="1" /><rect x="17" y="16" width="6" height="6" rx="1" /></svg>
                <span className="min-w-0 flex-1"><span className="block truncate text-[11px] font-semibold text-ops-text">{group.label}</span>{group.instanceLabel ? <span className="mt-0.5 block truncate text-[9px] font-normal text-ops-muted/55">{group.instanceLabel}</span> : null}</span>
                <span className="rounded border border-ops-border/30 px-1.5 py-0.5 text-[9px] text-ops-muted">{groupAssets.length}</span>
              </button>
            </h3> : <h3 className="border-y border-ops-border/20 bg-ops-bg/35 px-3 py-1.5 text-[9px] font-bold tracking-[0.1em] text-ops-muted/65">{group.label}</h3>}
            <ul id={`organization-assets-${groupKey}`} hidden={!expanded} className={`${expanded ? 'flex' : 'hidden'} flex-col list-none m-0 p-0 ${organizationTree ? 'ml-5 border-l border-ops-cyan/15' : ''}`}>
              {groupAssets.map((asset) => {
                const selected = asset.id === selectedAssetId
                const managedByJumpServer = asset.authType === 'jumpserver'
                const menuOpen = !managedByJumpServer && asset.id === menuAssetId

                return (
                  <li key={asset.id} className="relative group">
                    <div className={`relative flex items-center transition-all duration-200 ${selected ? 'bg-ops-cyan/5 shadow-[inset_2px_0_0_0_rgb(var(--ops-cyan))]' : 'hover:bg-ops-panel/40'} ${menuOpen ? 'bg-ops-panel/80' : ''}`}>
                      <ListItemCard
                        title={connectingAssetIds.includes(asset.id) ? `${asset.name} · 连接中…` : asset.name}
                        aria-busy={connectingAssetIds.includes(asset.id)}
                        disabled={connectingAssetIds.includes(asset.id)}
                        meta={getAssetMeta(asset, t('assets.localSystem'))}
                        active={selected}
                        onClick={() => onSelectAsset(asset.id)}
                        onContextMenu={(event) => {
                          event.preventDefault()
                          if (!managedByJumpServer) setMenuAssetId(asset.id)
                        }}
                      />

                      {!managedByJumpServer ? <button
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
                      </button> : null}
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
