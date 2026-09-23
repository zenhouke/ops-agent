import { requestJson, requestVoid } from './client'

export type HostKeyChallenge = {
  token: string
  hostname: string
  algorithm: string
  fingerprint: string
}

export type TerminalSessionResponse = {
  terminal_id: string | null
  channel: string | null
  error: string
  host_key?: HostKeyChallenge | null
}

export async function confirmTerminalHostKey(assetId: number | null, token: string): Promise<void> {
  return requestVoid('/api/terminal/host-key/confirm', {
    method: 'POST',
    body: JSON.stringify({ asset_id: assetId, token }),
  })
}

export async function createTerminalSession(assetId: number): Promise<TerminalSessionResponse> {
  return requestJson<TerminalSessionResponse>('/api/terminal/sessions', {
    method: 'POST',
    body: JSON.stringify({ asset_id: assetId }),
  })
}

export async function closeTerminalSession(terminalSessionId: string): Promise<void> {
  return requestVoid(`/api/terminal/sessions/${terminalSessionId}`, {
    method: 'DELETE',
  })
}

export async function reconnectTerminalSession(terminalSessionId: string, assetId: number): Promise<TerminalSessionResponse> {
  return requestJson<TerminalSessionResponse>(`/api/terminal/sessions/${terminalSessionId}/reconnect`, {
    method: 'POST',
    body: JSON.stringify({ asset_id: assetId }),
  })
}
