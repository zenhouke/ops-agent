import { requestJson } from './client'

export type JumpServerInstance = {
  id: number
  authMode: 'access_key' | 'ssh_gateway'
  name: string
  baseUrl: string
  orgId: string
  accessKeyId: string
  accessKeySecretMasked: string
  verifyTls: boolean
  enabled: boolean
  connectionStatus: string
  lastError: string
  lastSyncAt: string | null
  assetCount: number
}

export type JumpServerInstancePayload = {
  name: string
  auth_mode: 'access_key' | 'ssh_gateway'
  base_url: string
  org_id: string
  access_key_id: string
  access_key_secret?: string
  verify_tls: boolean
  enabled: boolean
}

export type JumpServerAccount = {
  id?: string | null
  name?: string | null
  username?: string | null
  alias?: string | null
  secret_type?: string | null
  privileged?: boolean | null
  is_active?: boolean | null
}

export type JumpServerAssetBinding = {
  id: number
  assetId: number
  externalAssetId: string
  name: string
  address: string
  platform: string
  category: string
  type: string
  accounts: JumpServerAccount[]
  accountRef: string
  accountUsername: string
  active: boolean
}

export type JumpServerOperation = {
  success: boolean
  message: string
  created: number
  updated: number
  total: number
  skipped: number
}

export const listJumpServerInstances = () => requestJson<JumpServerInstance[]>('/api/jumpserver/instances')

export const createJumpServerInstance = (payload: JumpServerInstancePayload) =>
  requestJson<JumpServerInstance>('/api/jumpserver/instances', { method: 'POST', body: JSON.stringify(payload) })

export const updateJumpServerInstance = (id: number, payload: Partial<JumpServerInstancePayload>) =>
  requestJson<JumpServerInstance>(`/api/jumpserver/instances/${id}`, { method: 'PUT', body: JSON.stringify(payload) })

export const testJumpServerInstance = (id: number) =>
  requestJson<JumpServerOperation>(`/api/jumpserver/instances/${id}/test`, { method: 'POST' })

export const syncJumpServerInstance = (id: number) =>
  requestJson<JumpServerOperation>(`/api/jumpserver/instances/${id}/sync`, { method: 'POST' })

export const listJumpServerAssets = (id: number) =>
  requestJson<JumpServerAssetBinding[]>(`/api/jumpserver/instances/${id}/assets`)

export const selectJumpServerAccount = (bindingId: number, accountRef: string) =>
  requestJson<JumpServerAssetBinding>(`/api/jumpserver/assets/${bindingId}/account`, {
    method: 'PATCH',
    body: JSON.stringify({ account_ref: accountRef }),
  })
