import { requestJson, requestVoid } from './client'
import type { Asset, AssetContext, AssetType } from '../types/ops'

export type AssetPayload = {
  name: string
  asset_type: AssetType
  group_id?: number | null
  ssh_key_id?: number | null
  proxy_asset_id?: number | null
  host?: string
  port?: number
  username?: string
  auth_type?: string
  credential_secret?: string
  tags?: string[]
  vendor?: string
  description?: string
}

export type AssetConnectionTestResult = {
  success: boolean
  message: string
  detected_device_type: string | null
  detected_asset_type: string | null
  prompt: string | null
}

type AssetDto = {
  id: number
  group_id: number | null
  ssh_key_id: number | null
  proxy_asset_id: number | null
  name: string
  asset_type: AssetType
  host: string
  port: number
  username: string
  auth_type: string
  tags: string[]
  vendor: string
  description: string
}

type AssetContextDto = {
  asset: AssetDto
  terminal_session: {
    id: number
    status: string
    last_error: string
    started_at: string
    ended_at: string | null
  } | null
  recent_terminal_events: Array<{
    id: number
    event_type: string
    event_data: string
    created_at: string
  }>
  assistant_sessions: Array<{
    id: number
    title: string
    active_model: string
  }>
}

export function mapAsset(dto: AssetDto): Asset {
  return {
    id: dto.id,
    groupId: dto.group_id,
    sshKeyId: dto.ssh_key_id,
    proxyAssetId: dto.proxy_asset_id,
    name: dto.name,
    assetType: dto.asset_type,
    host: dto.host,
    port: dto.port,
    username: dto.username,
    authType: dto.auth_type,
    tags: dto.tags,
    vendor: dto.vendor,
    description: dto.description,
  }
}

export async function getAssets(): Promise<Asset[]> {
  const assets = await requestJson<AssetDto[]>('/api/assets')
  return assets.map(mapAsset)
}

export function testAssetConnection(asset: AssetPayload, assetId?: number | null): Promise<AssetConnectionTestResult> {
  return requestJson<AssetConnectionTestResult>('/api/assets/connection-test', {
    method: 'POST',
    body: JSON.stringify({ asset_id: assetId ?? null, asset }),
  })
}

export async function getAssetContext(assetId: number): Promise<AssetContext> {
  const context = await requestJson<AssetContextDto>(`/api/assets/${assetId}/context`)
  return {
    asset: mapAsset(context.asset),
    terminalSession: context.terminal_session
      ? {
          id: context.terminal_session.id,
          status: context.terminal_session.status,
          lastError: context.terminal_session.last_error,
          startedAt: context.terminal_session.started_at,
          endedAt: context.terminal_session.ended_at,
        }
      : null,
    recentTerminalEvents: context.recent_terminal_events.map((item) => ({
      id: item.id,
      eventType: item.event_type,
      eventData: item.event_data,
      createdAt: item.created_at,
    })),
    assistantSessions: context.assistant_sessions.map((item) => ({ id: item.id, title: item.title, model: item.active_model })),
  }
}

export async function createAsset(payload: AssetPayload): Promise<Asset> {
  const asset = await requestJson<AssetDto>('/api/assets', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return mapAsset(asset)
}

export async function updateAsset(assetId: number, payload: AssetPayload): Promise<Asset> {
  const asset = await requestJson<AssetDto>(`/api/assets/${assetId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
  return mapAsset(asset)
}

export async function deleteAsset(assetId: number): Promise<void> {
  await requestVoid(`/api/assets/${assetId}`, {
    method: 'DELETE',
  })
}
