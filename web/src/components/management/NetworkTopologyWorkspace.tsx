import { useEffect, useMemo, useState } from 'react'
import type { Asset } from '../../types/ops'
import {
  collectTopologySnapshot,
  getTopologySnapshot,
  listTopologySnapshots,
  type TopologySnapshot,
} from '../../api/networkTopology'

const NETWORK_TYPES = new Set(['network', 'cisco', 'huawei', 'h3c', 'juniper'])
const CONCURRENCY_OPTIONS = [1, 2, 4, 8]

export function NetworkTopologyWorkspace({ assets }: { assets: Asset[] }) {
  const networkAssets = useMemo(
    () => assets.filter((asset) => NETWORK_TYPES.has(asset.assetType)),
    [assets],
  )
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [snapshots, setSnapshots] = useState<TopologySnapshot[]>([])
  const [current, setCurrent] = useState<TopologySnapshot | null>(null)
  const [maxConcurrency, setMaxConcurrency] = useState(4)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [showLinkLabels, setShowLinkLabels] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    void listTopologySnapshots()
      .then(async (items) => {
        if (!active) return
        setSnapshots(items)
        if (items[0]) {
          const latest = await getTopologySnapshot(items[0].id)
          if (active) setCurrent(latest)
        }
      })
      .catch((reason) => {
        if (active) setError(reason instanceof Error ? reason.message : String(reason))
      })
    return () => { active = false }
  }, [])

  useEffect(() => {
    const available = new Set(networkAssets.map((asset) => asset.id))
    setSelectedIds((ids) => ids.filter((id) => available.has(id)))
  }, [networkAssets])

  const selectedAssets = networkAssets.filter((asset) => selectedIds.includes(asset.id))
  const positions = useMemo(() => {
    const nodes = current?.nodes ?? []
    return new Map(nodes.map((node, index) => {
      const angle = (index / Math.max(nodes.length, 1)) * Math.PI * 2 - Math.PI / 2
      return [node.id, { x: 400 + Math.cos(angle) * 270, y: 245 + Math.sin(angle) * 175 }]
    }))
  }, [current])

  const openSnapshot = async (id: number) => {
    setError('')
    try {
      setCurrent(await getTopologySnapshot(id))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    }
  }

  const collect = async () => {
    if (!selectedIds.length) return
    setConfirming(false)
    setBusy(true)
    setError('')
    try {
      const snapshot = await collectTopologySnapshot(selectedIds, '', maxConcurrency)
      setCurrent(snapshot)
      setSnapshots(await listTopologySnapshots())
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  const statusClass = current?.status === 'completed'
    ? 'text-ops-green'
    : current?.status === 'failed'
      ? 'text-ops-danger'
      : 'text-ops-warning'

  return <section className="relative flex h-full min-h-0 flex-col bg-ops-bg">
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-ops-border/35 bg-ops-panel/60 px-5 py-3">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-ops-cyan/70">Network discovery</div>
        <h1 className="mt-0.5 text-[15px] font-semibold text-ops-text">网络拓扑</h1>
      </div>
      <div className="flex items-center gap-2">
        <label className="flex items-center gap-1.5 text-[10px] text-ops-muted/70">
          并发数
          <select
            value={maxConcurrency}
            disabled={busy}
            onChange={(event) => setMaxConcurrency(Number(event.target.value))}
            className="rounded-[4px] border border-ops-border/45 bg-ops-deep px-2 py-1.5 text-[11px] text-ops-text outline-none"
          >
            {CONCURRENCY_OPTIONS.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
        <button
          type="button"
          disabled={busy || !selectedIds.length}
          onClick={() => setConfirming(true)}
          className="rounded-[4px] border border-ops-cyan/35 bg-ops-cyan/10 px-3 py-1.5 text-[11px] font-bold text-ops-cyan disabled:opacity-40"
        >
          {busy ? '并发采集中…' : `采集所选设备（${selectedIds.length}）`}
        </button>
      </div>
    </header>

    <div className="grid min-h-0 flex-1 grid-cols-[260px_minmax(0,1fr)]">
      <aside className="overflow-y-auto border-r border-ops-border/30 bg-ops-panel/30 p-3">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-[10px] font-bold text-ops-muted/60">采集资产</span>
          <span className="flex gap-2 text-[9px]">
            <button type="button" onClick={() => setSelectedIds(networkAssets.map((asset) => asset.id))} className="text-ops-cyan/75 hover:text-ops-cyan">全选</button>
            <button type="button" onClick={() => setSelectedIds([])} className="text-ops-muted/60 hover:text-ops-text">清空</button>
          </span>
        </div>
        <div className="space-y-1">
          {networkAssets.map((asset) => <label key={asset.id} className="flex cursor-pointer items-center gap-2 rounded-[4px] px-2 py-1.5 text-[11px] text-ops-text/80 hover:bg-ops-border/15">
            <input
              type="checkbox"
              checked={selectedIds.includes(asset.id)}
              onChange={() => setSelectedIds((ids) => ids.includes(asset.id) ? ids.filter((id) => id !== asset.id) : [...ids, asset.id])}
            />
            <span className="truncate">{asset.name}</span>
            <span className="ml-auto text-[9px] text-ops-muted/50">{asset.assetType}</span>
          </label>)}
        </div>
        <div className="my-3 h-px bg-ops-border/25" />
        <div className="mb-2 text-[10px] font-bold text-ops-muted/60">历史快照</div>
        <div className="space-y-1">
          {snapshots.map((snapshot) => <button
            type="button"
            key={snapshot.id}
            onClick={() => void openSnapshot(snapshot.id)}
            className={`w-full rounded-[4px] border px-2 py-2 text-left ${current?.id === snapshot.id ? 'border-ops-cyan/30 bg-ops-cyan/8' : 'border-transparent hover:bg-ops-border/15'}`}
          >
            <div className="truncate text-[11px] font-semibold text-ops-text/80">{snapshot.name}</div>
            <div className="mt-0.5 text-[9px] text-ops-muted/50">{snapshot.status} · {new Date(snapshot.createdAt).toLocaleString()}</div>
          </button>)}
        </div>
      </aside>

      <main className="min-h-0 overflow-auto p-4">
        {error ? <div className="mb-3 rounded border border-ops-danger/30 bg-ops-danger/8 p-2 text-[11px] text-ops-danger">{error}</div> : null}
        {!current ? <div className="flex h-full items-center justify-center text-[12px] text-ops-muted/55">选择设备后执行一次明确确认的只读采集。</div> : <>
          <div className="mb-3 flex flex-wrap items-center gap-3 text-[10px] text-ops-muted/60">
            <span>{current.nodes?.length ?? 0} 节点</span>
            <span>{current.links?.length ?? 0} 链路</span>
            <span className={statusClass}>{current.status}</span>
            {(current.links?.length ?? 0) > 0 ? <button
              type="button"
              className="ml-auto rounded border border-ops-border/30 px-2 py-1 text-[10px] text-ops-muted hover:border-ops-border/50 hover:text-ops-text"
              aria-pressed={showLinkLabels}
              onClick={() => setShowLinkLabels((visible) => !visible)}
            >{showLinkLabels ? '隐藏链路标签' : '显示链路标签'}</button> : null}
          </div>
          {(current.nodes?.length ?? 0) > 0 ? <svg viewBox="0 0 800 490" className="min-h-[490px] w-full rounded-[5px] border border-ops-border/30 bg-ops-deep/55">
            {(current.links ?? []).map((link) => {
              const a = positions.get(link.source)
              const b = positions.get(link.target)
              if (!a || !b) return null
              const label = `${link.protocol} ${link.sourceInterface} ↔ ${link.targetInterface}`
              return <g key={link.id}>
                <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="rgba(100,210,220,.4)" strokeWidth="2">
                  <title>{label}</title>
                </line>
                {showLinkLabels ? <text x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 - 5} textAnchor="middle" fill="rgba(180,200,210,.65)" fontSize="9">{label}</text> : null}
              </g>
            })}
            {(current.nodes ?? []).map((node) => {
              const position = positions.get(node.id)
              if (!position) return null
              return <g key={node.id}>
                <circle cx={position.x} cy={position.y} r="34" fill={node.external ? '#202733' : '#12343b'} stroke={node.external ? '#67717f' : '#42c7d3'} strokeWidth="1.5" />
                <text x={position.x} y={position.y - 2} textAnchor="middle" fill="#e7f1f3" fontSize="11" fontWeight="600">{node.name.slice(0, 16)}</text>
                <text x={position.x} y={position.y + 13} textAnchor="middle" fill="#8ba3aa" fontSize="8">{node.external ? 'external' : node.vendor}</text>
              </g>
            })}
          </svg> : <div className="flex min-h-[300px] items-center justify-center rounded-[5px] border border-ops-border/30 bg-ops-deep/40 text-center text-[12px] text-ops-muted/60">
            本次没有采集到有效节点，请查看下方错误后重新选择设备。
          </div>}
          {current.errors.length ? <div className="mt-3 rounded border border-ops-warning/25 bg-ops-warning/5 p-3">
            <div className="mb-2 text-[10px] font-bold text-ops-warning">采集错误（{current.errors.length}）</div>
            <ul className="max-h-44 space-y-1 overflow-y-auto text-[10px] text-ops-warning/90">
              {current.errors.map((item, index) => <li key={`${item.assetId ?? 'unknown'}-${index}`}><span className="font-semibold">{item.assetName ?? item.assetId}：</span>{item.message}</li>)}
            </ul>
          </div> : null}
        </>}
      </main>
    </div>

    {confirming ? <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/65 p-6" role="presentation">
      <div role="dialog" aria-modal="true" aria-labelledby="topology-confirm-title" className="w-full max-w-lg rounded-[6px] border border-ops-border/55 bg-ops-panel p-5 shadow-2xl">
        <h2 id="topology-confirm-title" className="text-[14px] font-semibold text-ops-text">确认只读拓扑采集</h2>
        <p className="mt-2 text-[11px] leading-5 text-ops-muted/75">
          将通过 JumpServer 连接 {selectedAssets.length} 台设备，最多同时采集 {maxConcurrency} 台。系统只执行版本、接口和 LLDP/CDP 邻居查询，不进入配置模式。
        </p>
        <div className="mt-3 max-h-40 overflow-y-auto rounded-[4px] border border-ops-border/35 bg-ops-deep/60 p-2 text-[10px] text-ops-text/75">
          {selectedAssets.map((asset) => <div key={asset.id} className="flex justify-between gap-3 py-0.5"><span className="truncate">{asset.name}</span><span className="shrink-0 text-ops-muted/55">{asset.assetType}</span></div>)}
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={() => setConfirming(false)} className="rounded-[4px] border border-ops-border/45 px-3 py-1.5 text-[11px] text-ops-muted hover:text-ops-text">取消</button>
          <button type="button" onClick={() => void collect()} className="rounded-[4px] border border-ops-cyan/40 bg-ops-cyan/15 px-3 py-1.5 text-[11px] font-semibold text-ops-cyan">开始采集</button>
        </div>
      </div>
    </div> : null}
  </section>
}
