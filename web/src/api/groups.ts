import { requestJson, requestVoid } from './client'
import type { AssetGroup } from '../types/ops'

export type AssetGroupPayload = {
  name: string
  description: string
  proxy_type?: 'none' | 'http_connect' | 'socks5'
  proxy_host?: string
  proxy_port?: number
  proxy_username?: string
  proxy_password?: string
}

export type AssetGroupDto = {
  id: number
  name: string
  description: string
  created_at: string
  updated_at: string
  proxy_type: 'none' | 'http_connect' | 'socks5'
  proxy_host: string
  proxy_port: number
  proxy_username: string
}

export function mapAssetGroup(group: AssetGroupDto): AssetGroup {
  return {
    id: group.id,
    name: group.name,
    description: group.description,
    createdAt: group.created_at,
    updatedAt: group.updated_at,
    proxyType: group.proxy_type, proxyHost: group.proxy_host, proxyPort: group.proxy_port, proxyUsername: group.proxy_username,
  }
}

export async function getGroups(): Promise<AssetGroup[]> {
  const groups = await requestJson<AssetGroupDto[]>('/api/groups')
  return groups.map(mapAssetGroup)
}

export async function createGroup(payload: AssetGroupPayload): Promise<AssetGroup> {
  const group = await requestJson<AssetGroupDto>('/api/groups', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return mapAssetGroup(group)
}

export async function updateGroup(groupId: number, payload: AssetGroupPayload): Promise<AssetGroup> {
  const group = await requestJson<AssetGroupDto>(`/api/groups/${groupId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
  return mapAssetGroup(group)
}

export async function deleteGroup(groupId: number): Promise<void> {
  await requestVoid(`/api/groups/${groupId}`, { method: 'DELETE' })
}
