import { useEffect, useMemo, useState } from 'react'
import type { Asset } from '../../types/ops'
import {
  collectTopologySnapshot,
  getTopologySnapshot,
  listTopologySnapshots,
  type TopologyLink,
  type TopologyNode,
  type TopologySnapshot,
} from '../../api/networkTopology'

const NETWORK_TYPES = new Set(['network', 'cisco', 'huawei', 'h3c', 'juniper'])
const CONCURRENCY_OPTIONS = [1, 2, 4, 8]
type TopologyLayerId = 'external' | 'router' | 'core' | 'aggregation' | 'access'
type TopologyLinkGroup = {
  key: string
  source: string
  target: string
  links: TopologyLink[]
}

const TOPOLOGY_LAYERS: Array<{
  id: TopologyLayerId
  label: string
  description: string
  color: string
}> = [
  { id: 'router', label: '边界路由层', description: '出口路由、网关与边界设备', color: '#d9a441' },
  { id: 'core', label: '核心交换层', description: '骨干转发与高连接度设备', color: '#42c7d3' },
  { id: 'aggregation', label: '汇聚交换层', description: '连接核心与接入层', color: '#6fa8dc' },
  { id: 'access', label: '接入交换层', description: '接入交换机与其他已采集设备', color: '#72b985' },
  { id: 'external', label: '外部网络 / 未纳管邻居', description: '运营商、WAN 或本次未采集设备', color: '#8794a5' },
]

function topologyNodeText(node: TopologyNode): string {
  return `${node.name} ${node.host} ${node.vendor} ${node.model}`.toLowerCase()
}

function inferTopologyLayer(node: TopologyNode, degree: number, maxDegree: number): TopologyLayerId {
  const text = topologyNodeText(node)
  if (/(router|rtr|gateway|border|wan|\bedge\b|\basr\d*\b|\bisr\d*\b|\bar\d{2,}\b|\bne\d{2,}\b|路由|网关|出口)/i.test(text)) return 'router'
  if (/(core|\bcsw[-_\d]|spine|backbone|核心|骨干)/i.test(text)) return 'core'
  if (/(aggregation|aggregate|distribution|\bdist[-_\d]|汇聚)/i.test(text)) return 'aggregation'
  if (/(access|leaf|torsw|topsw|ipmi[-_]?sw|\bsw\d+|接入)/i.test(text)) return 'access'
  if (node.external) {
    if (/(qfx|n9\d{3}|ce\d{4})/i.test(text)) return degree === maxDegree && maxDegree > 1 ? 'core' : 'aggregation'
    return 'external'
  }
  if (maxDegree > 1 && degree === maxDegree) return 'core'
  if (degree > 1) return 'aggregation'
  return 'access'
}

function shortNodeLabel(value: string, limit: number): string {
  return value.length > limit ? `${value.slice(0, limit - 1)}…` : value
}

function topologyLinkPath(
  a: { x: number; y: number },
  b: { x: number; y: number },
  index: number,
): string {
  if (Math.abs(a.y - b.y) < 2) {
    const laneY = a.y + 42 + (index % 4) * 7
    return `M ${a.x} ${a.y + 34} L ${a.x} ${laneY} L ${b.x} ${laneY} L ${b.x} ${b.y + 34}`
  }
  const direction = b.y > a.y ? 1 : -1
  const startY = a.y + direction * 34
  const endY = b.y - direction * 34
  const laneOffset = ((index % 7) - 3) * 7
  const middleY = (startY + endY) / 2 + laneOffset
  return `M ${a.x} ${startY} C ${a.x} ${middleY}, ${b.x} ${middleY}, ${b.x} ${endY}`
}

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
  const [showPhysicalLinks, setShowPhysicalLinks] = useState(false)
  const [hoveredLinkKey, setHoveredLinkKey] = useState<string | null>(null)
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null)
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

  useEffect(() => {
    setFocusedNodeId(null)
    setHoveredLinkKey(null)
  }, [current?.id])

  const selectedAssets = networkAssets.filter((asset) => selectedIds.includes(asset.id))
  const topologyLayout = useMemo(() => {
    const nodes = current?.nodes ?? []
    const degree = new Map(nodes.map((node) => [node.id, 0]))
    for (const link of current?.links ?? []) {
      degree.set(link.source, (degree.get(link.source) ?? 0) + 1)
      degree.set(link.target, (degree.get(link.target) ?? 0) + 1)
    }
    const maxDegree = Math.max(0, ...degree.values())
    const grouped = new Map<TopologyLayerId, TopologyNode[]>(
      TOPOLOGY_LAYERS.map((layer) => [layer.id, []])
    )
    for (const node of nodes) {
      grouped.get(inferTopologyLayer(node, degree.get(node.id) ?? 0, maxDegree))?.push(node)
    }
    for (const layerNodes of grouped.values()) {
      layerNodes.sort((left, right) => left.name.localeCompare(right.name, 'zh-CN'))
    }
    const nodeLayer = new Map<string, number>()
    TOPOLOGY_LAYERS.forEach((layer, index) => {
      for (const node of grouped.get(layer.id) ?? []) nodeLayer.set(node.id, index)
    })
    const adjacency = new Map<string, string[]>()
    for (const link of current?.links ?? []) {
      adjacency.set(link.source, [...(adjacency.get(link.source) ?? []), link.target])
      adjacency.set(link.target, [...(adjacency.get(link.target) ?? []), link.source])
    }
    const precedingRank = new Map<string, number>()
    TOPOLOGY_LAYERS.forEach((layer, layerIndex) => {
      const layerNodes = grouped.get(layer.id) ?? []
      if (layerIndex > 0) {
        layerNodes.sort((left, right) => {
          const score = (node: TopologyNode) => {
            const upstream = (adjacency.get(node.id) ?? [])
              .filter((id) => (nodeLayer.get(id) ?? layerIndex) < layerIndex)
              .map((id) => precedingRank.get(id))
              .filter((value): value is number => value !== undefined)
            return upstream.length
              ? upstream.reduce((sum, value) => sum + value, 0) / upstream.length
              : Number.MAX_SAFE_INTEGER
          }
          return score(left) - score(right) || left.name.localeCompare(right.name, 'zh-CN')
        })
      }
      layerNodes.forEach((node, index) => precedingRank.set(node.id, index / Math.max(1, layerNodes.length - 1)))
    })
    const largestLayer = Math.max(1, ...Array.from(grouped.values(), (items) => items.length))
    const width = Math.max(1100, largestLayer * 210 + 300)
    const positions = new Map<string, { x: number; y: number; layer: TopologyLayerId }>()
    TOPOLOGY_LAYERS.forEach((layer, layerIndex) => {
      const layerNodes = grouped.get(layer.id) ?? []
      const availableWidth = width - 290
      layerNodes.forEach((node, nodeIndex) => {
        positions.set(node.id, {
          x: 240 + (availableWidth * (nodeIndex + 1)) / (layerNodes.length + 1),
          y: 90 + layerIndex * 170,
          layer: layer.id,
        })
      })
    })
    return { positions, grouped, degree, width, height: 860 }
  }, [current])

  const logicalLinkGroups = useMemo(() => {
    const groups = new Map<string, TopologyLinkGroup>()
    for (const link of current?.links ?? []) {
      const [first, second] = [link.source, link.target].sort()
      const key = `${first}::${second}`
      const existing = groups.get(key)
      if (existing) {
        existing.links.push(link)
      } else {
        groups.set(key, { key, source: link.source, target: link.target, links: [link] })
      }
    }
    return Array.from(groups.values())
  }, [current])

  const renderedLinkGroups = useMemo<TopologyLinkGroup[]>(() => {
    if (!showPhysicalLinks) return logicalLinkGroups
    return logicalLinkGroups.flatMap((group) => group.links.map((link) => ({
      key: `${group.key}::${link.id}`,
      source: link.source,
      target: link.target,
      links: [link],
    })))
  }, [logicalLinkGroups, showPhysicalLinks])

  const hoveredLinkGroup = renderedLinkGroups.find((group) => group.key === hoveredLinkKey) ?? null
  const nodeNames = useMemo(
    () => new Map((current?.nodes ?? []).map((node) => [node.id, node.name])),
    [current],
  )
  const focusedNodeName = focusedNodeId ? nodeNames.get(focusedNodeId) ?? focusedNodeId : null
  const sameLayerGroupCount = logicalLinkGroups.filter((group) => {
    const source = topologyLayout.positions.get(group.source)
    const target = topologyLayout.positions.get(group.target)
    return source && target && source.layer === target.layer
  }).length
  const focusedNeighborIds = useMemo(() => {
    if (!focusedNodeId) return new Set<string>()
    const neighbors = new Set<string>([focusedNodeId])
    for (const group of logicalLinkGroups) {
      if (group.source === focusedNodeId) neighbors.add(group.target)
      if (group.target === focusedNodeId) neighbors.add(group.source)
    }
    return neighbors
  }, [focusedNodeId, logicalLinkGroups])

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
            <span>{logicalLinkGroups.length} 组设备互联</span>
            <span className="text-violet-300/75">{sameLayerGroupCount} 组同层互联</span>
            <span className={statusClass}>{current.status}</span>
            {(current.links?.length ?? 0) > 0 ? <div className="ml-auto flex items-center gap-2">{focusedNodeId ? <button
              type="button"
              className="rounded border border-ops-cyan/35 bg-ops-cyan/8 px-2 py-1 text-[10px] text-ops-cyan hover:bg-ops-cyan/12"
              onClick={() => setFocusedNodeId(null)}
            >清除设备聚焦</button> : null}<button
              type="button"
              className="rounded border border-ops-border/30 px-2 py-1 text-[10px] text-ops-muted hover:border-ops-border/50 hover:text-ops-text"
              aria-pressed={showPhysicalLinks}
              onClick={() => {
                setHoveredLinkKey(null)
                setShowPhysicalLinks((visible) => !visible)
              }}
            >{showPhysicalLinks ? '合并同设备链路' : `展开物理链路（${current.links?.length ?? 0}）`}</button><button
              type="button"
              className="rounded border border-ops-border/30 px-2 py-1 text-[10px] text-ops-muted hover:border-ops-border/50 hover:text-ops-text"
              aria-pressed={showLinkLabels}
              onClick={() => setShowLinkLabels((visible) => !visible)}
            >{showLinkLabels ? '隐藏链路标签' : '显示链路标签'}</button></div> : null}
          </div>
          {(current.links?.length ?? 0) > 0 ? <div className="mb-3 min-h-[44px] rounded-[5px] border border-ops-border/25 bg-ops-panel/30 px-3 py-2 text-[10px] text-ops-muted/70">
            {hoveredLinkGroup ? <div className="flex flex-wrap items-start gap-x-4 gap-y-1">
              <span className="font-semibold text-ops-text">{nodeNames.get(hoveredLinkGroup.source) ?? hoveredLinkGroup.source} ↔ {nodeNames.get(hoveredLinkGroup.target) ?? hoveredLinkGroup.target}</span>
              <span className="text-ops-cyan">{hoveredLinkGroup.links.length} 条物理链路</span>
              <span className="w-full font-mono text-[9px] text-ops-muted/65">
                {hoveredLinkGroup.links.slice(0, 6).map((link) => `${link.protocol} ${link.sourceInterface} ↔ ${link.targetInterface}`).join(' · ')}
                {hoveredLinkGroup.links.length > 6 ? ` · 另 ${hoveredLinkGroup.links.length - 6} 条` : ''}
              </span>
            </div> : focusedNodeName
              ? <><span className="font-semibold text-ops-cyan">正在聚焦：{focusedNodeName}</span><span className="ml-3">仅突出该设备的直连互联；再次点击设备或点击“清除设备聚焦”恢复全图。</span></>
              : <><span className="text-violet-300">紫色线表示同层交换机互联。</span><span className="ml-2">点击设备可聚焦全部直连关系；悬停连线可查看协议和物理接口。</span></>}
          </div> : null}
          {(current.nodes?.length ?? 0) > 0 ? <div className="overflow-auto rounded-[5px] border border-ops-border/30 bg-ops-deep/55">
            <svg
              viewBox={`0 0 ${topologyLayout.width} ${topologyLayout.height}`}
              style={{ width: topologyLayout.width, minWidth: '100%', height: topologyLayout.height }}
              role="img"
              aria-label="按边界路由、核心、汇聚、接入和外部未纳管邻居排列的网络拓扑"
            >
            {TOPOLOGY_LAYERS.map((layer, index) => {
              const y = 12 + index * 170
              const count = topologyLayout.grouped.get(layer.id)?.length ?? 0
              return <g key={layer.id}>
                <rect x="8" y={y} width={topologyLayout.width - 16} height="148" rx="5" fill={index % 2 === 0 ? 'rgba(255,255,255,.018)' : 'rgba(255,255,255,.032)'} stroke="rgba(130,155,165,.13)" />
                <rect x="8" y={y} width="4" height="148" rx="2" fill={layer.color} opacity=".8" />
                <text x="26" y={y + 54} fill={layer.color} fontSize="12" fontWeight="700">{layer.label}</text>
                <text x="26" y={y + 76} fill="rgba(155,177,185,.62)" fontSize="9">{layer.description}</text>
                <text x="26" y={y + 100} fill="rgba(155,177,185,.45)" fontSize="8.5">{count} 个节点</text>
              </g>
            })}
            {renderedLinkGroups.map((group, index) => {
              const a = topologyLayout.positions.get(group.source)
              const b = topologyLayout.positions.get(group.target)
              if (!a || !b) return null
              const protocols = Array.from(new Set(group.links.map((link) => link.protocol.toUpperCase()))).join('/')
              const firstLink = group.links[0]
              const label = group.links.length > 1
                ? `${group.links.length} 条物理链路 · ${protocols}`
                : `${firstLink.protocol} ${firstLink.sourceInterface} ↔ ${firstLink.targetInterface}`
              const hovered = hoveredLinkKey === group.key
              const anotherHovered = hoveredLinkKey !== null && !hovered
              const connectedToFocusedNode = focusedNodeId === null
                || group.source === focusedNodeId
                || group.target === focusedNodeId
              const path = topologyLinkPath(a, b, index)
              const sameLayer = Math.abs(a.y - b.y) < 2
              const endpointA = sameLayer
                ? { x: a.x, y: a.y + 34 }
                : { x: a.x, y: a.y + (b.y > a.y ? 34 : -34) }
              const endpointB = sameLayer
                ? { x: b.x, y: b.y + 34 }
                : { x: b.x, y: b.y + (a.y > b.y ? 34 : -34) }
              const labelX = (a.x + b.x) / 2
              const labelY = sameLayer
                ? a.y + 34 + (index % 4) * 7
                : (a.y + b.y) / 2 - 8
              const linkColor = sameLayer ? '#b690f5' : protocols.includes('CDP') ? '#d9a441' : '#55cbd5'
              return <g
                key={group.key}
                onMouseEnter={() => setHoveredLinkKey(group.key)}
                onMouseLeave={() => setHoveredLinkKey(null)}
              >
                <path
                  d={path}
                  fill="none"
                  stroke="transparent"
                  strokeWidth="16"
                  className={connectedToFocusedNode ? 'cursor-crosshair' : ''}
                  pointerEvents={connectedToFocusedNode ? 'stroke' : 'none'}
                />
                <path d={path} fill="none" stroke={hovered ? '#f4e4a4' : linkColor} strokeWidth={hovered ? 3 : connectedToFocusedNode && focusedNodeId ? 2.4 : 1.8} opacity={hovered ? 1 : anotherHovered || !connectedToFocusedNode ? .07 : focusedNodeId ? .88 : .5} pointerEvents="none">
                  <title>{label}</title>
                </path>
                {hovered ? <>
                  <circle cx={endpointA.x} cy={endpointA.y} r="4" fill="#f4e4a4" />
                  <circle cx={endpointB.x} cy={endpointB.y} r="4" fill="#f4e4a4" />
                </> : null}
                {showLinkLabels || hovered ? <g pointerEvents="none">
                  <rect x={labelX - 112} y={labelY - 13} width="224" height="20" rx="4" fill="rgba(10,18,23,.92)" stroke={hovered ? '#f4e4a4' : 'rgba(100,210,220,.35)'} />
                  <text x={labelX} y={labelY + 1} textAnchor="middle" fill={hovered ? '#fff4bf' : 'rgba(200,220,225,.82)'} fontSize="8.5">{shortNodeLabel(label, 44)}</text>
                </g> : null}
              </g>
            })}
            {(current.nodes ?? []).map((node) => {
              const position = topologyLayout.positions.get(node.id)
              if (!position) return null
              const layer = TOPOLOGY_LAYERS.find((item) => item.id === position.layer)
                ?? TOPOLOGY_LAYERS.find((item) => item.id === 'access')!
              const detail = node.external ? '未纳管邻居' : [node.vendor, node.model].filter(Boolean).join(' · ') || '类型待识别'
              const focused = focusedNodeId === node.id
              const relatedToFocus = focusedNodeId === null || focusedNeighborIds.has(node.id)
              return <g
                key={node.id}
                role="button"
                tabIndex={0}
                aria-label={`聚焦设备 ${node.name}`}
                className="cursor-pointer outline-none"
                opacity={relatedToFocus ? 1 : .22}
                onClick={() => setFocusedNodeId((currentId) => currentId === node.id ? null : node.id)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    setFocusedNodeId((currentId) => currentId === node.id ? null : node.id)
                  }
                }}
              >
                <title>{`${node.name}\n${detail}\n自动归类：${layer.label}`}</title>
                <rect x={position.x - 76} y={position.y - 34} width="152" height="68" rx="7" fill={node.external ? '#202733' : '#12343b'} stroke={focused ? '#fff1a8' : layer.color} strokeWidth={focused ? 3 : 1.5} />
                <circle cx={position.x - 60} cy={position.y - 18} r="3.5" fill={layer.color} />
                <text x={position.x - 50} y={position.y - 14} fill={layer.color} fontSize="8" fontWeight="700">{shortNodeLabel(layer.label, 14)}</text>
                <text x={position.x + 60} y={position.y - 14} textAnchor="end" fill="#8ba3aa" fontSize="8">{topologyLayout.degree.get(node.id) ?? 0} 条链路</text>
                <text x={position.x} y={position.y + 7} textAnchor="middle" fill="#e7f1f3" fontSize="11" fontWeight="600">{shortNodeLabel(node.name, 22)}</text>
                <text x={position.x} y={position.y + 24} textAnchor="middle" fill="#8ba3aa" fontSize="8">{shortNodeLabel(detail, 26)}</text>
              </g>
            })}
            </svg>
          </div> : <div className="flex min-h-[300px] items-center justify-center rounded-[5px] border border-ops-border/30 bg-ops-deep/40 text-center text-[12px] text-ops-muted/60">
            本次没有采集到有效节点，请查看下方错误后重新选择设备。
          </div>}
          {(current.nodes?.length ?? 0) > 0 ? <p className="mt-2 text-[9px] leading-4 text-ops-muted/55">
            层级由设备名称、型号和链路连接度自动推断；“外部”表示未纳入本次采集，不等同于已确认的运营商设备。悬停节点可查看归类信息。
          </p> : null}
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
