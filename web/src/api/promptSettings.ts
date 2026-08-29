import { requestJson } from './client'

export type PromptSettingKey = 'agentBehavior' | 'incidentResponse' | 'knowledgeExtraction' | 'memoryUsage' | 'organizationRules'
export type PromptOverrides = Record<PromptSettingKey, string>

export type PromptSettings = {
  schemaVersion: number
  revision: number
  overrides: PromptOverrides
  defaults: PromptOverrides
  effective: PromptOverrides
  updatedAt: string | null
  immutableSafetySummary: string
  maxPromptChars: number
}

export function getPromptSettings(): Promise<PromptSettings> {
  return requestJson<PromptSettings>('/api/prompt-settings')
}

export function updatePromptSettings(revision: number, overrides: PromptOverrides): Promise<PromptSettings> {
  return requestJson<PromptSettings>('/api/prompt-settings', {
    method: 'PUT',
    body: JSON.stringify({ revision, overrides }),
  })
}

export function resetPromptSettings(revision: number): Promise<PromptSettings> {
  return requestJson<PromptSettings>('/api/prompt-settings/reset', {
    method: 'POST',
    body: JSON.stringify({ revision }),
  })
}
