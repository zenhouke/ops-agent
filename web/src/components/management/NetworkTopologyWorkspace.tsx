import { useEffect, useMemo, useState } from 'react'
import type { Asset } from '../../types/ops'
import { collectTopologySnapshot, getTopologySnapshot, listTopologySnapshots, type TopologySnapshot } from '../../api/networkTopology'

const NETWORK_TYPES = new Set(['network', 'cisco', 'huawei', 'h3c', 'juniper'])

export function NetworkTopologyWorkspace({ assets }: { assets: Asset[] }) {
  const networkAssets = assets.filter((asset) => NETWORK_TYPES.has(asset.assetType))
  const [selectedIds, setSelectedIds] = useState<number[]>(networkAssets.map((asset) => asset.id))
  const [snapshots, setSnapshots] = useState<TopologySnapshot[]>([])
  const [current, setCurrent] = useState<TopologySnapshot | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => { void listTopologySnapshots().then(setSnapshots).catch((reason) => setError(String(reason))) }, [])
  const positions = useMemo(() => {
    const nodes = current?.nodes ?? []
    return new Map(nodes.map((node, index) => {
      const angle = (index / Math.max(nodes.length, 1)) * Math.PI * 2 - Math.PI / 2
      return [node.id, { x: 400 + Math.cos(angle) * 270, y: 245 + Math.sin(angle) * 175 }]
    }))
  }, [current])

  const openSnapshot = async (id: number) => {
    setError('')
    try { setCurrent(await getTopologySnapshot(id)) } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)) }
  }
  const collect = async () => {
    if (!selectedIds.length) return
    setBusy(true); setError('')
    try {
      const snapshot = await collectTopologySnapshot(selectedIds)
      setCurrent(snapshot)
      setSnapshots(await listTopologySnapshots())
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)) } finally { setBusy(false) }
  }

  return <section className="flex h-full min-h-0 flex-col bg-ops-bg">
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-ops-border/35 bg-ops-panel/60 px-5 py-3">
      <div><div className="text-[10px] font-bold uppercase tracking-[0.14em] text-ops-cyan/70">Network discovery</div><h1 className="mt-0.5 text-[15px] font-semibold text-ops-text">网络拓扑</h1></div>
      <button type="button" disabled={busy || !selectedIds.length} onClick={() => void collect()} className="rounded-[4px] border border-ops-cyan/35 bg-ops-cyan/10 px-3 py-1.5 text-[11px] font-bold text-ops-cyan disabled:opacity-40">{busy ? '并发采集中…' : `采集所选设备（${selectedIds.length}）`}</button>
    </header>
    <div className="grid min-h-0 flex-1 grid-cols-[260px_minmax(0,1fr)]">
      <aside className="overflow-y-auto border-r border-ops-border/30 bg-ops-panel/30 p-3">
        <div className="mb-2 text-[10px] font-bold text-ops-muted/60">采集资产</div>
        <div className="space-y-1">{networkAssets.map((asset) => <label key={asset.id} className="flex cursor-pointer items-center gap-2 rounded-[4px] px-2 py-1.5 text-[11px] text-ops-text/80 hover:bg-ops-border/15"><input type="checkbox" checked={selectedIds.includes(asset.id)} onChange={() => setSelectedIds((ids) => ids.includes(asset.id) ? ids.filter((id) => id !== asset.id) : [...ids, asset.id])}/><span className="truncate">{asset.name}</span><span className="ml-auto text-[9px] text-ops-muted/50">{asset.assetType}</span></label>)}</div>
        <div className="my-3 h-px bg-ops-border/25" />
        <div className="mb-2 text-[10px] font-bold text-ops-muted/60">历史快照</div>
        <div className="space-y-1">{snapshots.map((snapshot) => <button type="button" key={snapshot.id} onClick={() => void openSnapshot(snapshot.id)} className={`w-full rounded-[4px] border px-2 py-2 text-left ${current?.id === snapshot.id ? 'border-ops-cyan/30 bg-ops-cyan/8' : 'border-transparent hover:bg-ops-border/15'}`}><div className="truncate text-[11px] font-semibold text-ops-text/80">{snapshot.name}</div><div className="mt-0.5 text-[9px] text-ops-muted/50">{snapshot.status} · {new Date(snapshot.createdAt).toLocaleString()}</div></button>)}</div>
      </aside>
      <main className="min-h-0 overflow-auto p-4">
        {error ? <div className="mb-3 rounded border border-ops-danger/30 bg-ops-danger/8 p-2 text-[11px] text-ops-danger">{error}</div> : null}
        {!current ? <div className="flex h-full items-center justify-center text-[12px] text-ops-muted/55">选择历史快照，或对明确勾选的网络资产执行一次只读采集。</div> : <>
          <div className="mb-3 flex items-center gap-3 text-[10px] text-ops-muted/60"><span>{current.nodes?.length ?? 0} 节点</span><span>{current.links?.length ?? 0} 链路</span><span className={current.status === 'completed' ? 'text-ops-green' : 'text-ops-warning'}>{current.status}</span></div>
          <svg viewBox="0 0 800 490" className="min-h-[490px] w-full rounded-[5px] border border-ops-border/30 bg-ops-deep/55">
            {(current.links ?? []).map((link) => { const a = positions.get(link.source); const b = positions.get(link.target); if (!a || !b) return null; return <g key={link.id}><line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="rgba(100,210,220,.4)" strokeWidth="2"/><text x={(a.x+b.x)/2} y={(a.y+b.y)/2-5} textAnchor="middle" fill="rgba(180,200,210,.65)" fontSize="9">{link.protocol} {link.sourceInterface} ↔ {link.targetInterface}</text></g> })}
            {(current.nodes ?? []).map((node) => { const p = positions.get(node.id)!; return <g key={node.id}><circle cx={p.x} cy={p.y} r="34" fill={node.external ? '#202733' : '#12343b'} stroke={node.external ? '#67717f' : '#42c7d3'} strokeWidth="1.5"/><text x={p.x} y={p.y-2} textAnchor="middle" fill="#e7f1f3" fontSize="11" fontWeight="600">{node.name.slice(0, 16)}</text><text x={p.x} y={p.y+13} textAnchor="middle" fill="#8ba3aa" fontSize="8">{node.external ? 'external' : node.vendor}</text></g> })}
          </svg>
          {current.errors.length ? <div className="mt-3 rounded border border-ops-warning/25 bg-ops-warning/5 p-2 text-[10px] text-ops-warning">{current.errors.map((item) => `${item.assetName ?? item.assetId}: ${item.message}`).join('；')}</div> : null}
        </>}
      </main>
    </div>
  </section>
}
