import { useEffect, useMemo, useRef, useState } from 'react'
import type { Asset } from '../../types/ops'

type MultiAssetTaskDialogProps = {
  assets: Asset[]
  initialPrimaryAssetId: number
  creating: boolean
  error: string | null
  onClose: () => void
  onCreate: (primaryAssetId: number, allowedAssetIds: number[]) => Promise<void>
}

function assetSubtitle(asset: Asset) {
  const target = asset.assetType === 'local_terminal'
    ? '当前设备'
    : `${asset.host || '地址未配置'}${asset.port ? `:${asset.port}` : ''}`
  return `${target} · ${asset.vendor || asset.assetType}`
}

export function MultiAssetTaskDialog({
  assets,
  initialPrimaryAssetId,
  creating,
  error,
  onClose,
  onCreate,
}: MultiAssetTaskDialogProps) {
  const [primaryAssetId, setPrimaryAssetId] = useState(initialPrimaryAssetId)
  const [selectedAssetIds, setSelectedAssetIds] = useState<Set<number>>(() => new Set([initialPrimaryAssetId]))
  const [query, setQuery] = useState('')
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    setPrimaryAssetId(initialPrimaryAssetId)
    setSelectedAssetIds(new Set([initialPrimaryAssetId]))
    setQuery('')
    searchRef.current?.focus()
  }, [initialPrimaryAssetId])

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !creating) onClose()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [creating, onClose])

  const filteredAssets = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase()
    if (!normalizedQuery) return assets
    return assets.filter((asset) => [
      asset.name,
      asset.host,
      asset.username,
      asset.vendor,
      asset.assetType,
      ...asset.tags,
    ].some((value) => value.toLocaleLowerCase().includes(normalizedQuery)))
  }, [assets, query])

  const changePrimaryAsset = (assetId: number) => {
    setPrimaryAssetId(assetId)
    setSelectedAssetIds((current) => new Set(current).add(assetId))
  }

  const toggleAsset = (assetId: number) => {
    if (assetId === primaryAssetId) return
    setSelectedAssetIds((current) => {
      const next = new Set(current)
      if (next.has(assetId)) next.delete(assetId)
      else next.add(assetId)
      return next
    })
  }

  const selectedCount = selectedAssetIds.size

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ops-bg/70 p-4 backdrop-blur-sm"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !creating) onClose()
      }}
    >
      <section
        className="flex h-[680px] max-h-[92vh] w-[760px] max-w-[96vw] flex-col overflow-hidden rounded-lg border border-ops-border/45 bg-ops-panel shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="multi-asset-task-title"
      >
        <header className="flex shrink-0 items-start justify-between border-b border-ops-border/25 bg-ops-deep/55 px-5 py-4">
          <div>
            <h3 id="multi-asset-task-title" className="text-[15px] font-semibold text-ops-text">新建多资产任务</h3>
            <p className="mt-1 text-[11px] text-ops-muted">在一个任务上下文中分析多台设备，范围外资产不能被 Agent 访问。</p>
          </div>
          <button type="button" className="desktop-icon-button" onClick={onClose} disabled={creating} aria-label="关闭">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12" /></svg>
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto p-5">
          <div className="rounded border border-ops-cyan/25 bg-ops-cyan/[0.045] px-3.5 py-3 text-[11px] leading-5 text-ops-muted">
            <strong className="text-ops-text">授权边界：</strong>这里勾选的是会话可用范围，不会立即连接设备，也不会自动执行命令。Agent 请求终端时仍需你确认，危险命令仍走独立审批。
          </div>

          <label className="mt-5 block">
            <span className="mb-1.5 block text-[10px] font-bold tracking-[0.08em] text-ops-muted">主资产</span>
            <select
              value={primaryAssetId}
              onChange={(event) => changePrimaryAsset(Number(event.target.value))}
              className="h-10 w-full rounded border border-ops-border/45 bg-ops-deep px-3 text-xs text-ops-text outline-none transition focus:border-ops-cyan/60"
            >
              {assets.map((asset) => <option key={asset.id} value={asset.id}>{asset.name} · {asset.host || '当前设备'}</option>)}
            </select>
            <span className="mt-1.5 block text-[10px] text-ops-muted/70">任务默认从主资产开始；主资产始终在白名单中。</span>
          </label>

          <div className="mt-5 flex items-end justify-between gap-3">
            <label className="min-w-0 flex-1">
              <span className="mb-1.5 block text-[10px] font-bold tracking-[0.08em] text-ops-muted">任务资产范围</span>
              <div className="relative">
                <svg className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ops-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></svg>
                <input
                  ref={searchRef}
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="搜索名称、地址、厂商或标签"
                  className="h-10 w-full rounded border border-ops-border/45 bg-ops-deep pl-9 pr-3 text-xs text-ops-text outline-none placeholder:text-ops-muted/45 focus:border-ops-cyan/60"
                />
              </div>
            </label>
            <span className="shrink-0 pb-2 text-[11px] font-semibold text-ops-cyan">已选择 {selectedCount} 台</span>
          </div>

          <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2" role="group" aria-label="选择任务资产">
            {filteredAssets.map((asset) => {
              const checked = selectedAssetIds.has(asset.id)
              const primary = asset.id === primaryAssetId
              return (
                <label
                  key={asset.id}
                  className={`flex min-w-0 cursor-pointer items-center gap-3 rounded border px-3 py-2.5 transition ${checked ? 'border-ops-cyan/45 bg-ops-cyan/[0.06]' : 'border-ops-border/30 bg-ops-deep/35 hover:border-ops-border/60'} ${primary ? 'cursor-default' : ''}`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={primary}
                    onChange={() => toggleAsset(asset.id)}
                    className="h-3.5 w-3.5 shrink-0 accent-[rgb(var(--ops-cyan))]"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2">
                      <span className="truncate text-[11px] font-semibold text-ops-text">{asset.name}</span>
                      {primary ? <span className="shrink-0 rounded border border-ops-warning/35 px-1.5 py-0.5 text-[8px] font-bold text-ops-warning">主资产</span> : null}
                    </span>
                    <span className="mt-0.5 block truncate text-[9px] text-ops-muted/70">{assetSubtitle(asset)}</span>
                  </span>
                </label>
              )
            })}
            {filteredAssets.length === 0 ? (
              <div className="col-span-full py-10 text-center text-xs text-ops-muted">没有匹配的资产</div>
            ) : null}
          </div>
        </div>

        <footer className="flex shrink-0 items-center justify-between gap-4 border-t border-ops-border/25 bg-ops-deep/45 px-5 py-3.5">
          <div className="min-w-0 text-[10px] text-ops-muted">
            创建后显示为“多资产 · {selectedCount} 台”，白名单只属于这个任务。
            {error ? <span className="mt-1 block text-ops-danger" role="alert">{error}</span> : null}
          </div>
          <div className="flex shrink-0 gap-2">
            <button type="button" className="desktop-toolbar-button px-4" onClick={onClose} disabled={creating}>取消</button>
            <button
              type="button"
              className="rounded bg-ops-cyan px-4 py-2 text-[11px] font-bold text-ops-bg transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={creating || selectedCount === 0}
              onClick={() => void onCreate(primaryAssetId, [...selectedAssetIds])}
            >
              {creating ? '正在创建…' : `创建任务 · ${selectedCount} 台`}
            </button>
          </div>
        </footer>
      </section>
    </div>
  )
}
