import type { OpsPlugin } from '../types/ops'
import { requestJson } from './client'

type OpsPluginsResponse = {
  plugins: OpsPlugin[]
  summary: {
    plugins: number
    validPlugins: number
    enabledPlugins: number
    tools: number
  }
}

export async function getOpsPlugins(refresh = false): Promise<OpsPluginsResponse> {
  return requestJson<OpsPluginsResponse>(
    refresh ? '/api/plugins/reload' : '/api/plugins',
    refresh ? { method: 'POST' } : undefined,
  )
}
