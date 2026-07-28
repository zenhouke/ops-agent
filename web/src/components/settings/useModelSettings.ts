import { type FormEvent, useCallback, useEffect, useRef, useState } from 'react'
import {
  createModelConfig,
  deleteModelConfig,
  discoverModelConfigModels,
  getModelConfigs,
  setDefaultModelConfig,
  testModelConfig,
  updateModelConfig,
} from '../../api'
import type { ModelConfig } from '../../types/ops'
import { modelProviderPresets } from '../../types/modelProviderPresets'
import type { ModelForm, SettingsDialogProps } from './settingsTypes'

const defaultPreset = modelProviderPresets[0]
const emptyModelForm: ModelForm = {
  name: '',
  provider: defaultPreset.provider,
  baseUrl: defaultPreset.baseUrl,
  apiKey: '',
  modelName: defaultPreset.modelName,
  isDefault: false,
  timeoutSeconds: '30',
  temperature: '0.2',
  maxTokens: '1024',
  description: '',
  providerOptions: {},
}

function modelToForm(config: ModelConfig): ModelForm {
  return {
    name: config.name,
    provider: config.provider,
    baseUrl: config.baseUrl,
    apiKey: '',
    modelName: config.modelName,
    isDefault: config.isDefault,
    timeoutSeconds: String(config.timeoutSeconds),
    temperature: String(config.temperature),
    maxTokens: String(config.maxTokens),
    description: config.description,
    providerOptions: {},
  }
}

type ModelSettingsOptions = Pick<
  SettingsDialogProps,
  'onModelOptionsChange' | 'onSelectedModelChange'
>

export function useModelSettings({
  onModelOptionsChange,
  onSelectedModelChange,
}: ModelSettingsOptions) {
  const modelOptionsChangeRef = useRef(onModelOptionsChange)
  modelOptionsChangeRef.current = onModelOptionsChange
  const [modelConfigs, setModelConfigs] = useState<ModelConfig[]>([])
  const [modelForm, setModelForm] = useState<ModelForm>(emptyModelForm)
  const [showModelForm, setShowModelForm] = useState(false)
  const [editingModel, setEditingModel] = useState<ModelConfig | null>(null)
  const [deletingModel, setDeletingModel] = useState<ModelConfig | null>(null)
  const [testResult, setTestResult] = useState<string | null>(null)
  const [discoveredModels, setDiscoveredModels] = useState<string[]>([])
  const [discoveringModels, setDiscoveringModels] = useState(false)
  const [discoveryMessage, setDiscoveryMessage] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadModels = useCallback(async () => {
    try {
      const models = await getModelConfigs()
      setModelConfigs(models)
      modelOptionsChangeRef.current(models.map((config) => config.modelName))
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Failed to load models')
    }
  }, [])

  useEffect(() => {
    void loadModels()
  }, [loadModels])

  const runSaving = async (action: () => Promise<void>, fallback: string) => {
    setSaving(true)
    setError(null)
    try {
      await action()
    } catch (operationError) {
      setError(operationError instanceof Error ? operationError.message : fallback)
    } finally {
      setSaving(false)
    }
  }

  const resetForm = () => {
    setEditingModel(null)
    setShowModelForm(false)
    setTestResult(null)
    setDiscoveredModels([])
    setDiscoveryMessage(null)
    setModelForm(emptyModelForm)
  }

  const startCreate = () => {
    resetForm()
    setDeletingModel(null)
    setModelForm({ ...emptyModelForm, modelName: '' })
    setShowModelForm(true)
  }

  const startEdit = (config: ModelConfig) => {
    setEditingModel(config)
    setDeletingModel(null)
    setTestResult(null)
    setDiscoveredModels([config.modelName])
    setDiscoveryMessage(null)
    setModelForm(modelToForm(config))
    setShowModelForm(true)
  }

  const handleProviderChange = (provider: string) => {
    const preset = modelProviderPresets.find((item) => item.provider === provider)
    setDiscoveredModels([])
    setDiscoveryMessage(null)
    setModelForm((current) => ({
      ...current,
      provider,
      baseUrl: preset?.baseUrl ?? current.baseUrl,
      modelName: '',
    }))
  }

  const updateConnectionField = (
    updates: Partial<Pick<ModelForm, 'baseUrl' | 'apiKey'>>,
  ) => {
    setDiscoveredModels([])
    setDiscoveryMessage(null)
    setModelForm((current) => ({ ...current, ...updates, modelName: '' }))
  }

  const payload = () => ({
    name: modelForm.name.trim(),
    provider: modelForm.provider,
    baseUrl: modelForm.baseUrl.trim(),
    apiKey: modelForm.apiKey.trim() || undefined,
    modelName: modelForm.modelName.trim(),
    isDefault: modelForm.isDefault,
    timeoutSeconds: Number(modelForm.timeoutSeconds) || 30,
    temperature: Number(modelForm.temperature) || 0.2,
    maxTokens: Number(modelForm.maxTokens) || 1024,
    description: modelForm.description.trim(),
  })

  const discover = async () => {
    setDiscoveringModels(true)
    setDiscoveryMessage(null)
    setTestResult(null)
    setError(null)
    try {
      const result = await discoverModelConfigModels({
        provider: modelForm.provider,
        baseUrl: modelForm.baseUrl.trim(),
        apiKey: modelForm.apiKey.trim(),
        timeoutSeconds: Number(modelForm.timeoutSeconds) || 30,
        providerOptions: modelForm.providerOptions,
      })
      setDiscoveredModels(result.models)
      setModelForm((current) => ({
        ...current,
        modelName: result.models.includes(current.modelName)
          ? current.modelName
          : result.models[0] ?? '',
      }))
      setDiscoveryMessage(
        result.models.length > 0
          ? `Discovered ${result.models.length} models.`
          : 'No models were returned by this provider.',
      )
    } catch (discoverError) {
      setDiscoveredModels([])
      setModelForm((current) => ({ ...current, modelName: '' }))
      setError(discoverError instanceof Error ? discoverError.message : 'Model discovery failed')
    } finally {
      setDiscoveringModels(false)
    }
  }

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    await runSaving(async () => {
      const saved = editingModel
        ? await updateModelConfig(editingModel.id, payload())
        : await createModelConfig(payload())
      const next = editingModel
        ? modelConfigs.map((config) => config.id === saved.id
          ? saved
          : { ...config, isDefault: saved.isDefault ? false : config.isDefault })
        : [saved, ...modelConfigs.map((config) => ({
          ...config,
          isDefault: saved.isDefault ? false : config.isDefault,
        }))]
      setModelConfigs(next)
      onModelOptionsChange(next.map((config) => config.modelName))
      if (saved.isDefault) onSelectedModelChange(saved.modelName)
      resetForm()
    }, 'Failed to save model')
  }

  const setDefault = async (config: ModelConfig) => {
    await runSaving(async () => {
      const selected = await setDefaultModelConfig(config.id)
      const next = modelConfigs.map((item) => ({ ...item, isDefault: item.id === selected.id }))
      setModelConfigs(next)
      onModelOptionsChange(next.map((item) => item.modelName))
      onSelectedModelChange(selected.modelName)
    }, 'Failed to set default model')
  }

  const confirmDelete = async () => {
    if (!deletingModel || deletingModel.isDefault) return
    await runSaving(async () => {
      await deleteModelConfig(deletingModel.id)
      const next = modelConfigs.filter((config) => config.id !== deletingModel.id)
      setModelConfigs(next)
      onModelOptionsChange(next.map((config) => config.modelName))
      setDeletingModel(null)
    }, 'Failed to delete model')
  }

  const test = async () => {
    setTestResult(null)
    await runSaving(async () => {
      const result = await testModelConfig({
        provider: modelForm.provider,
        baseUrl: modelForm.baseUrl.trim(),
        apiKey: modelForm.apiKey.trim(),
        modelName: modelForm.modelName.trim(),
        timeoutSeconds: Number(modelForm.timeoutSeconds) || 30,
        temperature: Number(modelForm.temperature) || 0.2,
        maxTokens: Number(modelForm.maxTokens) || 1024,
        providerOptions: modelForm.providerOptions,
      })
      setTestResult(result.message)
    }, 'Connection test failed')
  }

  return {
    modelConfigs,
    modelForm,
    setModelForm,
    showModelForm,
    editingModel,
    deletingModel,
    setDeletingModel,
    testResult,
    discoveredModels,
    discoveringModels,
    discoveryMessage,
    saving,
    error,
    loadModels,
    startCreate,
    startEdit,
    resetForm,
    handleProviderChange,
    updateConnectionField,
    discover,
    save,
    setDefault,
    confirmDelete,
    test,
  }
}
