import { requestJson, requestVoid } from './client'
import { mapTimestamps } from './mappers'
import type { ModelConfig } from '../types/ops'

export type ModelConfigPayload = {
  name: string
  provider: string
  baseUrl: string
  apiKey?: string
  modelName: string
  isDefault: boolean
  timeoutSeconds: number
  temperature: number
  maxTokens: number
  description: string
}

export type ModelConnectionTestPayload = {
  provider: string
  baseUrl: string
  apiKey: string
  modelName: string
  timeoutSeconds: number
  temperature: number
  maxTokens: number
  providerOptions?: Record<string, unknown>
}

export type ModelDiscoveryPayload = {
  configId?: number
  provider: string
  baseUrl: string
  apiKey: string
  timeoutSeconds: number
  providerOptions?: Record<string, unknown>
}

export type ModelConnectionTestResult = {
  success: boolean
  message: string
}

export type ModelDiscoveryResult = {
  models: string[]
}

type ModelConfigDto = {
  id: number
  name: string
  provider: string
  base_url: string
  api_key_masked: string
  model_name: string
  is_default: boolean
  timeout_seconds: number
  temperature: number
  max_tokens: number
  description: string
  created_at: string | null
  updated_at: string | null
}

type ModelConfigRequest = {
  name: string
  provider: string
  base_url: string
  api_key?: string
  model_name: string
  is_default: boolean
  timeout_seconds: number
  temperature: number
  max_tokens: number
  description: string
}

type ModelConnectionTestRequest = {
  provider: string
  base_url: string
  api_key: string
  model_name: string
  timeout_seconds: number
  temperature: number
  max_tokens: number
  provider_options?: Record<string, unknown>
}

type ModelDiscoveryRequest = {
  config_id?: number
  provider: string
  base_url: string
  api_key?: string
  timeout_seconds: number
  provider_options?: Record<string, unknown>
}

function toModelConfigRequest(payload: ModelConfigPayload): ModelConfigRequest {
  return {
    name: payload.name,
    provider: payload.provider,
    base_url: payload.baseUrl,
    ...(payload.apiKey ? { api_key: payload.apiKey } : {}),
    model_name: payload.modelName,
    is_default: payload.isDefault,
    timeout_seconds: payload.timeoutSeconds,
    temperature: payload.temperature,
    max_tokens: payload.maxTokens,
    description: payload.description,
  }
}

function toConnectionTestRequest(payload: ModelConnectionTestPayload): ModelConnectionTestRequest {
  return {
    provider: payload.provider,
    base_url: payload.baseUrl,
    api_key: payload.apiKey,
    model_name: payload.modelName,
    timeout_seconds: payload.timeoutSeconds,
    temperature: payload.temperature,
    max_tokens: payload.maxTokens,
    provider_options: payload.providerOptions,
  }
}

function toModelDiscoveryRequest(payload: ModelDiscoveryPayload): ModelDiscoveryRequest {
  return {
    config_id: payload.configId,
    provider: payload.provider,
    base_url: payload.baseUrl,
    api_key: payload.apiKey || undefined,
    timeout_seconds: payload.timeoutSeconds,
    provider_options: payload.providerOptions,
  }
}

export function mapModelConfig(config: ModelConfigDto): ModelConfig {
  return {
    id: config.id,
    name: config.name,
    provider: config.provider,
    baseUrl: config.base_url,
    apiKeyMasked: config.api_key_masked,
    modelName: config.model_name,
    isDefault: config.is_default,
    timeoutSeconds: config.timeout_seconds,
    temperature: config.temperature,
    maxTokens: config.max_tokens,
    description: config.description,
    ...mapTimestamps(config),
  }
}

export async function getModelConfigs(): Promise<ModelConfig[]> {
  const configs = await requestJson<ModelConfigDto[]>('/api/model-configs')
  return configs.map(mapModelConfig)
}

export async function createModelConfig(payload: ModelConfigPayload): Promise<ModelConfig> {
  const config = await requestJson<ModelConfigDto>('/api/model-configs', {
    method: 'POST',
    body: JSON.stringify(toModelConfigRequest(payload)),
  })
  return mapModelConfig(config)
}

export async function updateModelConfig(configId: number, payload: ModelConfigPayload): Promise<ModelConfig> {
  const config = await requestJson<ModelConfigDto>(`/api/model-configs/${configId}`, {
    method: 'PUT',
    body: JSON.stringify(toModelConfigRequest(payload)),
  })
  return mapModelConfig(config)
}

export async function deleteModelConfig(configId: number): Promise<void> {
  await requestVoid(`/api/model-configs/${configId}`, { method: 'DELETE' })
}

export async function setDefaultModelConfig(configId: number): Promise<ModelConfig> {
  const config = await requestJson<ModelConfigDto>(`/api/model-configs/${configId}/default`, { method: 'POST' })
  return mapModelConfig(config)
}

export async function discoverModelConfigModels(payload: ModelDiscoveryPayload): Promise<ModelDiscoveryResult> {
  return requestJson<ModelDiscoveryResult>('/api/model-configs/discover', {
    method: 'POST',
    body: JSON.stringify(toModelDiscoveryRequest(payload)),
  })
}

export async function testModelConfig(payload: ModelConnectionTestPayload): Promise<ModelConnectionTestResult> {
  return requestJson<ModelConnectionTestResult>('/api/model-configs/test', {
    method: 'POST',
    body: JSON.stringify(toConnectionTestRequest(payload)),
  })
}

export async function getAvailableModels(): Promise<string[]> {
  const result = await requestJson<{ available_models: string[] }>('/api/models')
  return result.available_models
}
