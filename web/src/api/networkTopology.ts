import { requestJson } from './client'

export type TopologyNode = { id: string; assetId: number | null; name: string; host: string; vendor: string; model: string; serialNumber: string; softwareVersion: string; external: boolean; interfaces: Array<Record<string, unknown>> }
export type TopologyLink = { id: number; source: string; target: string; sourceInterface: string; targetInterface: string; protocol: string }
export type TopologySnapshot = { id: number; name: string; status: string; requestedAssetIds: number[]; errors: Array<{ assetId?: number; assetName?: string; message: string }>; createdAt: string; nodes?: TopologyNode[]; links?: TopologyLink[] }

export const listTopologySnapshots = () => requestJson<TopologySnapshot[]>('/api/network-topology/snapshots')
export const getTopologySnapshot = (id: number) => requestJson<TopologySnapshot>(`/api/network-topology/snapshots/${id}`)
export const collectTopologySnapshot = (assetIds: number[], name = '') => requestJson<TopologySnapshot>('/api/network-topology/snapshots', { method: 'POST', body: JSON.stringify({ assetIds, name, maxConcurrency: 4 }) })
