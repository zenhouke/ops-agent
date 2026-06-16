import { type FormEvent, useEffect, useState } from 'react'

import {
  createGroup,
  createMCPServer,
  createModelConfig,
  createSSHKey,
  deleteGroup,
  deleteMCPServer,
  deleteModelConfig,
  deleteSSHKey,
  discoverModelConfigModels,
  getApprovalPolicy,
  getGroups,
  getModelConfigs,
  getSSHKeys,
  listMCPServers,
  refreshMCPServer,
  setDefaultModelConfig,
  testModelConfig,
  setMCPServerEnabled,
  testMCPServer,
  updateApprovalPolicy,
  updateGroup,
  updateMCPServer,
  updateMCPTool,
  updateModelConfig,
  updateSSHKey,
} from '../../api'
import { useAppearance } from '../../hooks/useAppearance'
import { useSkillPackages } from '../../hooks/useSkillPackages'
import type { AssetGroup, MCPServer, MCPTool, ModelConfig, SSHKey } from '../../types/ops'
import { AppearanceSection } from './AppearanceSection'
import { DeleteConfirmDialog } from './DeleteConfirmDialog'
import { GroupsSection } from './GroupsSection'
import { McpSection } from './McpSection'
import { ModelsSection } from './ModelsSection'
import { PermissionsSection } from './PermissionsSection'
import { SkillsSection } from './SkillsSection'
import { SSHKeysSection } from './SSHKeysSection'
import { SchedulerSection } from './SchedulerSection'
import { modelProviderPresets } from '../../types/modelProviderPresets'
import type { GroupForm, MCPServerForm, ModelForm, PermissionsForm, SettingsDialogProps, SettingsSection, SSHKeyForm } from './settingsTypes'

const emptyGroupForm: GroupForm = {
  name: '',
  description: '',
}

const defaultModelProviderPreset = modelProviderPresets[0]

const emptyModelForm: ModelForm = {
  name: '',
  provider: defaultModelProviderPreset.provider,
  baseUrl: defaultModelProviderPreset.baseUrl,
  apiKey: '',
  modelName: defaultModelProviderPreset.modelName,
  isDefault: false,
  timeoutSeconds: '30',
  temperature: '0.2',
  maxTokens: '1024',
  description: '',
  providerOptions: {},
}

const emptySSHKeyForm: SSHKeyForm = {
  name: '',
  publicKey: '',
  privateKey: '',
  passphrase: '',
}

const emptyPermissionsForm: PermissionsForm = {
  allow: [],
  deny: [],
  allowInput: '',
  denyInput: '',
}

const emptyMCPServerForm: MCPServerForm = {
  name: '',
  transport: 'stdio',
  command: '',
  args: '',
  env: '{}',
  url: '',
  headers: '{}',
  timeoutSeconds: '30',
}

function sshKeyToForm(sshKey: SSHKey): SSHKeyForm {
  return {
    name: sshKey.name,
    publicKey: sshKey.publicKey,
    privateKey: '',
    passphrase: '',
  }
}

function getModelOptions(configs: ModelConfig[]) {
  return configs.map((config) => config.modelName)
}

function jsonToFormValue(value: Record<string, string>) {
  return JSON.stringify(value, null, 2)
}

function mcpServerToForm(server: MCPServer): MCPServerForm {
  return {
    name: server.name,
    transport: server.transport,
    command: server.command,
    args: server.args.join('\n'),
    env: jsonToFormValue(server.env),
    url: server.url,
    headers: jsonToFormValue(server.headers),
    timeoutSeconds: String(server.timeoutSeconds),
  }
}

function parseStringRecord(value: string, label: string) {
  const trimmed = value.trim()
  if (!trimmed) {
    return {}
  }
  const parsed: unknown = JSON.parse(trimmed)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(`${label} must be a JSON object`)
  }
  return Object.fromEntries(Object.entries(parsed).map(([key, entry]) => [key, String(entry)]))
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

type OperationDomain = 'groups' | 'models' | 'sshKeys' | 'permissions' | 'mcp'

const emptySavingByDomain: Record<OperationDomain, boolean> = {
  groups: false,
  models: false,
  sshKeys: false,
  permissions: false,
  mcp: false,
}

const emptyErrorByDomain: Record<OperationDomain, string | null> = {
  groups: null,
  models: null,
  sshKeys: null,
  permissions: null,
  mcp: null,
}

export function SettingsDialog({ initialGroups, selectedModel, sshKeys: initialSSHKeys, assets, onSelectedModelChange, onGroupsChange, onModelOptionsChange, onSSHKeysChange, onClose }: SettingsDialogProps) {
  const { language, themeMode, resolvedTheme, setLanguage, setThemeMode, t } = useAppearance()
  const [activeSection, setActiveSection] = useState<SettingsSection>('appearance')
  const [groups, setGroups] = useState<AssetGroup[]>(initialGroups)
  const [modelConfigs, setModelConfigs] = useState<ModelConfig[]>([])
  const [sshKeys, setSSHKeys] = useState<SSHKey[]>(initialSSHKeys)
  const { skillPackages: skills, loading: skillsLoading, error: skillsError, loadSkillPackages } = useSkillPackages()
  const [mcpServers, setMCPServers] = useState<MCPServer[]>([])
  const [loading, setLoading] = useState(true)
  const [mcpLoading, setMCPLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [mcpError, setMCPError] = useState<string | null>(null)
  const [savingByDomain, setSavingByDomain] = useState<Record<OperationDomain, boolean>>(emptySavingByDomain)
  const [errorByDomain, setErrorByDomain] = useState<Record<OperationDomain, string | null>>(emptyErrorByDomain)
  const [groupForm, setGroupForm] = useState<GroupForm>(emptyGroupForm)
  const [showGroupForm, setShowGroupForm] = useState(false)
  const [editingGroup, setEditingGroup] = useState<AssetGroup | null>(null)
  const [deletingGroup, setDeletingGroup] = useState<AssetGroup | null>(null)
  const [modelForm, setModelForm] = useState<ModelForm>(emptyModelForm)
  const [showModelForm, setShowModelForm] = useState(false)
  const [editingModel, setEditingModel] = useState<ModelConfig | null>(null)
  const [deletingModel, setDeletingModel] = useState<ModelConfig | null>(null)
  const [sshKeyForm, setSSHKeyForm] = useState<SSHKeyForm>(emptySSHKeyForm)
  const [showSSHKeyForm, setShowSSHKeyForm] = useState(false)
  const [editingSSHKey, setEditingSSHKey] = useState<SSHKey | null>(null)
  const [deletingSSHKey, setDeletingSSHKey] = useState<SSHKey | null>(null)
  const [permissionsForm, setPermissionsForm] = useState<PermissionsForm>(emptyPermissionsForm)
  const [mcpServerForm, setMCPServerForm] = useState<MCPServerForm>(emptyMCPServerForm)
  const [showMCPServerForm, setShowMCPServerForm] = useState(false)
  const [editingMCPServer, setEditingMCPServer] = useState<MCPServer | null>(null)
  const [deletingMCPServer, setDeletingMCPServer] = useState<MCPServer | null>(null)
  const [selectedMCPServerId, setSelectedMCPServerId] = useState<string | null>(null)
  const [modelTestResult, setModelTestResult] = useState<string | null>(null)
  const [mcpTestResult, setMCPTestResult] = useState<string | null>(null)
  const [discoveredModels, setDiscoveredModels] = useState<string[]>([])
  const [discoveringModels, setDiscoveringModels] = useState(false)
  const [modelDiscoveryMessage, setModelDiscoveryMessage] = useState<string | null>(null)

  const loadSettings = async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const [nextGroups, nextModels, nextSSHKeys, nextApprovalPolicy] = await Promise.all([getGroups(), getModelConfigs(), getSSHKeys(), getApprovalPolicy()])
      setGroups(nextGroups)
      onGroupsChange(nextGroups)
      setModelConfigs(nextModels)
      onModelOptionsChange(getModelOptions(nextModels))
      setSSHKeys(nextSSHKeys)
      onSSHKeysChange(nextSSHKeys)
      setPermissionsForm({ allow: nextApprovalPolicy.permissions.allow, deny: nextApprovalPolicy.permissions.deny, allowInput: '', denyInput: '' })
    } catch (loadError) {
      setLoadError(loadError instanceof Error ? loadError.message : 'Failed to load settings')
    } finally {
      setLoading(false)
    }
  }

  const loadMCPServers = async () => {
    setMCPLoading(true)
    setMCPError(null)
    try {
      const nextMCPServers = await listMCPServers()
      setMCPServers(nextMCPServers)
      setSelectedMCPServerId((current) => current ?? nextMCPServers[0]?.id ?? null)
    } catch (loadError) {
      setMCPError(loadError instanceof Error ? loadError.message : 'Failed to load MCP servers')
    } finally {
      setMCPLoading(false)
    }
  }

  const loadSkills = async () => {
    await loadSkillPackages(true)
  }

  useEffect(() => {
    void loadSettings()
    void loadSkills()
    void loadMCPServers()
  }, [])

  const runWithSaving = async (domain: OperationDomain, action: () => Promise<void>, fallbackMessage: string) => {
    setSavingByDomain((current) => ({ ...current, [domain]: true }))
    setErrorByDomain((current) => ({ ...current, [domain]: null }))
    try {
      await action()
    } catch (actionError) {
      setErrorByDomain((current) => ({
        ...current,
        [domain]: actionError instanceof Error ? actionError.message : fallbackMessage,
      }))
    } finally {
      setSavingByDomain((current) => ({ ...current, [domain]: false }))
    }
  }

  const startCreateGroup = () => {
    setEditingGroup(null)
    setDeletingGroup(null)
    setGroupForm(emptyGroupForm)
    setShowGroupForm(true)
  }

  const startEditGroup = (group: AssetGroup) => {
    setEditingGroup(group)
    setDeletingGroup(null)
    setGroupForm({ name: group.name, description: group.description })
    setShowGroupForm(true)
  }

  const cancelGroupForm = () => {
    setEditingGroup(null)
    setShowGroupForm(false)
    setGroupForm(emptyGroupForm)
  }

  const saveGroup = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    await runWithSaving('groups', async () => {
      const payload = { name: groupForm.name.trim(), description: groupForm.description.trim() }
      const savedGroup = editingGroup
        ? await updateGroup(editingGroup.id, payload)
        : await createGroup(payload)
      const nextGroups = editingGroup
        ? groups.map((group) => (group.id === savedGroup.id ? savedGroup : group))
        : [savedGroup, ...groups]
      setGroups(nextGroups)
      onGroupsChange(nextGroups)
      cancelGroupForm()
    }, 'Failed to save group')
  }

  const confirmDeleteGroup = async () => {
    if (!deletingGroup) {
      return
    }
    await runWithSaving('groups', async () => {
      await deleteGroup(deletingGroup.id)
      const nextGroups = groups.filter((group) => group.id !== deletingGroup.id)
      setGroups(nextGroups)
      onGroupsChange(nextGroups)
      setDeletingGroup(null)
    }, 'Failed to delete group')
  }

  const startCreateModel = () => {
    setEditingModel(null)
    setDeletingModel(null)
    setModelTestResult(null)
    setDiscoveredModels([])
    setModelDiscoveryMessage(null)
    setModelForm({ ...emptyModelForm, modelName: '' })
    setShowModelForm(true)
  }

  const startCreateSSHKey = () => {
    setEditingSSHKey(null)
    setDeletingSSHKey(null)
    setSSHKeyForm(emptySSHKeyForm)
    setShowSSHKeyForm(true)
  }

  const startEditSSHKey = (sshKey: SSHKey) => {
    setEditingSSHKey(sshKey)
    setDeletingSSHKey(null)
    setSSHKeyForm(sshKeyToForm(sshKey))
    setShowSSHKeyForm(true)
  }

  const cancelSSHKeyForm = () => {
    setEditingSSHKey(null)
    setShowSSHKeyForm(false)
    setSSHKeyForm(emptySSHKeyForm)
  }

  const startEditModel = (config: ModelConfig) => {
    setEditingModel(config)
    setDeletingModel(null)
    setModelTestResult(null)
    setDiscoveredModels([config.modelName])
    setModelDiscoveryMessage(null)
    setModelForm(modelToForm(config))
    setShowModelForm(true)
  }

  const cancelModelForm = () => {
    setEditingModel(null)
    setShowModelForm(false)
    setModelTestResult(null)
    setDiscoveredModels([])
    setModelDiscoveryMessage(null)
    setModelForm(emptyModelForm)
  }

  const handleModelProviderChange = (provider: string) => {
    const preset = modelProviderPresets.find((item) => item.provider === provider)
    setDiscoveredModels([])
    setModelDiscoveryMessage(null)
    setModelForm((current) => ({
      ...current,
      provider,
      baseUrl: preset?.baseUrl ?? current.baseUrl,
      modelName: '',
      providerOptions: current.providerOptions,
    }))
  }

  const updateModelConnectionField = (updates: Partial<Pick<ModelForm, 'baseUrl' | 'apiKey'>>) => {
    setDiscoveredModels([])
    setModelDiscoveryMessage(null)
    setModelForm((current) => ({ ...current, ...updates, modelName: '' }))
  }

  const toModelPayload = () => ({
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

  const discoverModels = async () => {
    setDiscoveringModels(true)
    setModelDiscoveryMessage(null)
    setModelTestResult(null)
    setErrorByDomain((current) => ({ ...current, models: null }))
    try {
      const result = await discoverModelConfigModels({
        provider: modelForm.provider,
        baseUrl: modelForm.baseUrl.trim(),
        apiKey: modelForm.apiKey.trim(),
        timeoutSeconds: Number(modelForm.timeoutSeconds) || 30,
        providerOptions: modelForm.providerOptions,
      })
      setDiscoveredModels(result.models)
      setModelForm((current) => ({ ...current, modelName: result.models.includes(current.modelName) ? current.modelName : result.models[0] ?? '' }))
      setModelDiscoveryMessage(result.models.length > 0 ? `Discovered ${result.models.length} models.` : 'No models were returned by this provider.')
    } catch (discoverError) {
      setDiscoveredModels([])
      setModelForm((current) => ({ ...current, modelName: '' }))
      setModelDiscoveryMessage(null)
      setErrorByDomain((current) => ({
        ...current,
        models: discoverError instanceof Error ? discoverError.message : 'Model discovery failed',
      }))
    } finally {
      setDiscoveringModels(false)
    }
  }

  const saveModel = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    await runWithSaving('models', async () => {
      const savedConfig = editingModel
        ? await updateModelConfig(editingModel.id, toModelPayload())
        : await createModelConfig(toModelPayload())
      const nextModels = editingModel
        ? modelConfigs.map((config) => (config.id === savedConfig.id ? savedConfig : { ...config, isDefault: savedConfig.isDefault ? false : config.isDefault }))
        : [savedConfig, ...modelConfigs.map((config) => ({ ...config, isDefault: savedConfig.isDefault ? false : config.isDefault }))]
      setModelConfigs(nextModels)
      onModelOptionsChange(getModelOptions(nextModels))
      if (savedConfig.isDefault) {
        onSelectedModelChange(savedConfig.modelName)
      }
      cancelModelForm()
    }, 'Failed to save model')
  }

  const setDefaultModel = async (config: ModelConfig) => {
    await runWithSaving('models', async () => {
      const defaultConfig = await setDefaultModelConfig(config.id)
      const nextModels = modelConfigs.map((item) => ({ ...item, isDefault: item.id === defaultConfig.id }))
      setModelConfigs(nextModels)
      onModelOptionsChange(getModelOptions(nextModels))
      onSelectedModelChange(defaultConfig.modelName)
    }, 'Failed to set default model')
  }

  const confirmDeleteModel = async () => {
    if (!deletingModel || deletingModel.isDefault) {
      return
    }
    await runWithSaving('models', async () => {
      await deleteModelConfig(deletingModel.id)
      const nextModels = modelConfigs.filter((config) => config.id !== deletingModel.id)
      setModelConfigs(nextModels)
      onModelOptionsChange(getModelOptions(nextModels))
      setDeletingModel(null)
    }, 'Failed to delete model')
  }

  const testModel = async () => {
    setModelTestResult(null)
    await runWithSaving('models', async () => {
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
      setModelTestResult(result.message)
    }, 'Connection test failed')
  }

  const saveSSHKey = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    await runWithSaving('sshKeys', async () => {
      const payload = {
        name: sshKeyForm.name.trim(),
        public_key: sshKeyForm.publicKey.trim(),
        private_key: sshKeyForm.privateKey.trim() || undefined,
        passphrase: sshKeyForm.passphrase.trim() || undefined,
      }
      const savedSSHKey = editingSSHKey
        ? await updateSSHKey(editingSSHKey.id, payload)
        : await createSSHKey({
          name: payload.name,
          public_key: payload.public_key,
          private_key: sshKeyForm.privateKey.trim(),
          passphrase: payload.passphrase,
        })
      const nextSSHKeys = editingSSHKey
        ? sshKeys.map((item) => (item.id === savedSSHKey.id ? savedSSHKey : item))
        : [savedSSHKey, ...sshKeys]
      setSSHKeys(nextSSHKeys)
      onSSHKeysChange(nextSSHKeys)
      cancelSSHKeyForm()
    }, 'Failed to save SSH key')
  }

  const confirmDeleteSSHKey = async () => {
    if (!deletingSSHKey) {
      return
    }
    await runWithSaving('sshKeys', async () => {
      await deleteSSHKey(deletingSSHKey.id)
      const nextSSHKeys = sshKeys.filter((item) => item.id !== deletingSSHKey.id)
      setSSHKeys(nextSSHKeys)
      onSSHKeysChange(nextSSHKeys)
      setDeletingSSHKey(null)
    }, 'Failed to delete SSH key')
  }

  const savePermissions = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    await runWithSaving('permissions', async () => {
      await updateApprovalPolicy({ permissions: { allow: permissionsForm.allow, deny: permissionsForm.deny } })
      setPermissionsForm({ ...permissionsForm, allowInput: '', denyInput: '' })
    }, 'Failed to save permissions')
  }

  const updateMCPServerInList = (server: MCPServer) => {
    setMCPServers((current) => current.map((item) => (item.id === server.id ? server : item)))
    setSelectedMCPServerId(server.id)
  }

  const startCreateMCPServer = () => {
    setEditingMCPServer(null)
    setDeletingMCPServer(null)
    setMCPTestResult(null)
    setMCPServerForm(emptyMCPServerForm)
    setShowMCPServerForm(true)
  }

  const startEditMCPServer = (server: MCPServer) => {
    setEditingMCPServer(server)
    setDeletingMCPServer(null)
    setMCPTestResult(null)
    setMCPServerForm(mcpServerToForm(server))
    setShowMCPServerForm(true)
    setSelectedMCPServerId(server.id)
  }

  const cancelMCPServerForm = () => {
    setEditingMCPServer(null)
    setShowMCPServerForm(false)
    setMCPTestResult(null)
    setMCPServerForm(emptyMCPServerForm)
  }

  const toMCPServerCreatePayload = () => ({
    name: mcpServerForm.name.trim(),
    transport: mcpServerForm.transport,
    command: mcpServerForm.transport === 'stdio' ? mcpServerForm.command.trim() : '',
    args: mcpServerForm.transport === 'stdio' ? mcpServerForm.args.split('\n').map((arg) => arg.trim()).filter(Boolean) : [],
    env: mcpServerForm.transport === 'stdio' ? parseStringRecord(mcpServerForm.env, 'Env') : {},
    url: mcpServerForm.transport === 'httpSse' ? mcpServerForm.url.trim() : '',
    headers: mcpServerForm.transport === 'httpSse' ? parseStringRecord(mcpServerForm.headers, 'Headers') : {},
    timeoutSeconds: Number(mcpServerForm.timeoutSeconds) || 30,
  })

  const toMCPServerUpdatePayload = (server: MCPServer) => {
    const originalForm = mcpServerToForm(server)
    const transportChanged = server.transport !== mcpServerForm.transport
    const payload = {
      name: mcpServerForm.name.trim(),
      transport: mcpServerForm.transport,
      command: mcpServerForm.transport === 'stdio' ? mcpServerForm.command.trim() : '',
      args: mcpServerForm.transport === 'stdio' ? mcpServerForm.args.split('\n').map((arg) => arg.trim()).filter(Boolean) : [],
      url: mcpServerForm.transport === 'httpSse' ? mcpServerForm.url.trim() : '',
      timeoutSeconds: Number(mcpServerForm.timeoutSeconds) || 30,
      ...(mcpServerForm.transport !== 'stdio' ? { env: {} } : transportChanged || mcpServerForm.env !== originalForm.env ? { env: parseStringRecord(mcpServerForm.env, 'Env') } : {}),
      ...(mcpServerForm.transport !== 'httpSse' ? { headers: {} } : transportChanged || mcpServerForm.headers !== originalForm.headers ? { headers: parseStringRecord(mcpServerForm.headers, 'Headers') } : {}),
    }
    return payload
  }

  const saveMCPServer = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    await runWithSaving('mcp', async () => {
      const savedServer = editingMCPServer
        ? await updateMCPServer(editingMCPServer.id, toMCPServerUpdatePayload(editingMCPServer))
        : await createMCPServer(toMCPServerCreatePayload())
      setMCPServers((current) => (editingMCPServer ? current.map((server) => (server.id === savedServer.id ? savedServer : server)) : [savedServer, ...current]))
      setSelectedMCPServerId(savedServer.id)
      cancelMCPServerForm()
    }, 'Failed to save MCP server')
  }

  const confirmDeleteMCPServer = async () => {
    if (!deletingMCPServer) {
      return
    }
    await runWithSaving('mcp', async () => {
      await deleteMCPServer(deletingMCPServer.id)
      const nextServers = mcpServers.filter((server) => server.id !== deletingMCPServer.id)
      setMCPServers(nextServers)
      setSelectedMCPServerId((current) => (current === deletingMCPServer.id ? nextServers[0]?.id ?? null : current))
      setDeletingMCPServer(null)
    }, 'Failed to delete MCP server')
  }

  const testMCP = async (server: MCPServer) => {
    setMCPTestResult(null)
    await runWithSaving('mcp', async () => {
      const result = await testMCPServer(server.id)
      if (result.server) {
        updateMCPServerInList(result.server)
      }
      setMCPTestResult(result.message)
    }, 'MCP server test failed')
  }

  const refreshMCP = async (server: MCPServer) => {
    await runWithSaving('mcp', async () => {
      updateMCPServerInList(await refreshMCPServer(server.id))
    }, 'Failed to refresh MCP server')
  }

  const setMCPEnabled = async (server: MCPServer, enabled: boolean) => {
    await runWithSaving('mcp', async () => {
      updateMCPServerInList(await setMCPServerEnabled(server.id, enabled))
    }, 'Failed to update MCP server')
  }

  const updateMCPToolSettings = async (tool: MCPTool, updates: { enabled?: boolean; approvalPolicy?: 'allow' | 'ask' | 'deny' }) => {
    await runWithSaving('mcp', async () => {
      updateMCPServerInList(await updateMCPTool(tool.id, updates))
    }, 'Failed to update MCP tool')
  }

  const sectionError = activeSection === 'groups'
    ? errorByDomain.groups
    : activeSection === 'models'
      ? errorByDomain.models
      : activeSection === 'sshKeys'
        ? errorByDomain.sshKeys
        : activeSection === 'permissions'
          ? errorByDomain.permissions
          : null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ops-bg/60 backdrop-blur-md animate-in fade-in duration-300" role="presentation">
      <section className="w-[880px] max-w-[95vw] h-[640px] max-h-[90vh] bg-ops-panel/90 border border-ops-border/40 rounded-2xl shadow-2xl flex flex-col overflow-hidden backdrop-blur-xl animate-in zoom-in-95 duration-300" role="dialog" aria-modal="true" aria-labelledby="settings-title">
        <div className="flex items-center justify-between p-6 border-b border-ops-border/20 bg-ops-panel shrink-0">
          <div>
            <h3 id="settings-title" className="text-[16px] font-bold  text-ops-cyan">{t('settings.title')}</h3>
            <p className="text-[11px] font-medium text-ops-muted mt-1 tracking-wider opacity-60">{t('settings.description')}</p>
          </div>
          <button type="button" className="h-8 px-4 text-[11px] font-bold  tracking-widest rounded-lg transition-all duration-200 text-ops-muted hover:text-ops-text hover:bg-ops-border/30 active:scale-95" onClick={onClose}>{t('common.close')}</button>
        </div>
        <div className="flex flex-1 flex-col overflow-hidden md:flex-row">
          <nav className="flex max-h-28 shrink-0 gap-2 overflow-x-auto overflow-y-hidden border-b border-ops-border/20 bg-ops-deep/40 p-3 md:max-h-none md:w-[220px] md:flex-col md:overflow-x-hidden md:overflow-y-auto md:border-b-0 md:border-r md:p-4" aria-label={t('settings.navigation')}>
            <button type="button" className={`w-full text-left px-4 py-3 rounded-xl transition-all duration-200 text-[11px] font-bold  active:scale-[0.98] ${activeSection === 'appearance' ? 'bg-ops-cyan/15 text-ops-cyan shadow-glow border border-ops-cyan/30' : 'text-ops-muted hover:text-ops-text hover:bg-ops-panel/60 border border-transparent'}`} onClick={() => setActiveSection('appearance')}>{t('settings.appearance')}</button>
            <button type="button" className={`w-full text-left px-4 py-3 rounded-xl transition-all duration-200 text-[11px] font-bold  active:scale-[0.98] ${activeSection === 'groups' ? 'bg-ops-cyan/15 text-ops-cyan shadow-glow border border-ops-cyan/30' : 'text-ops-muted hover:text-ops-text hover:bg-ops-panel/60 border border-transparent'}`} onClick={() => setActiveSection('groups')}>{t('settings.groups')}</button>
            <button type="button" className={`w-full text-left px-4 py-3 rounded-xl transition-all duration-200 text-[11px] font-bold  active:scale-[0.98] ${activeSection === 'models' ? 'bg-ops-cyan/15 text-ops-cyan shadow-glow border border-ops-cyan/30' : 'text-ops-muted hover:text-ops-text hover:bg-ops-panel/60 border border-transparent'}`} onClick={() => setActiveSection('models')}>{t('settings.models')}</button>
            <button type="button" className={`w-full text-left px-4 py-3 rounded-xl transition-all duration-200 text-[11px] font-bold  active:scale-[0.98] ${activeSection === 'sshKeys' ? 'bg-ops-cyan/15 text-ops-cyan shadow-glow border border-ops-cyan/30' : 'text-ops-muted hover:text-ops-text hover:bg-ops-panel/60 border border-transparent'}`} onClick={() => setActiveSection('sshKeys')}>{t('settings.sshKeys')}</button>
            <button type="button" className={`w-full text-left px-4 py-3 rounded-xl transition-all duration-200 text-[11px] font-bold  active:scale-[0.98] ${activeSection === 'permissions' ? 'bg-ops-cyan/15 text-ops-cyan shadow-glow border border-ops-cyan/30' : 'text-ops-muted hover:text-ops-text hover:bg-ops-panel/60 border border-transparent'}`} onClick={() => setActiveSection('permissions')}>{t('settings.permissions')}</button>
            <button type="button" className={`w-full text-left px-4 py-3 rounded-xl transition-all duration-200 text-[11px] font-bold  active:scale-[0.98] ${activeSection === 'skills' ? 'bg-ops-cyan/15 text-ops-cyan shadow-glow border border-ops-cyan/30' : 'text-ops-muted hover:text-ops-text hover:bg-ops-panel/60 border border-transparent'}`} onClick={() => setActiveSection('skills')}>{t('settings.skills')}</button>
            <button type="button" className={`w-full text-left px-4 py-3 rounded-xl transition-all duration-200 text-[11px] font-bold  active:scale-[0.98] ${activeSection === 'mcp' ? 'bg-ops-cyan/15 text-ops-cyan shadow-glow border border-ops-cyan/30' : 'text-ops-muted hover:text-ops-text hover:bg-ops-panel/60 border border-transparent'}`} onClick={() => setActiveSection('mcp')}>{t('settings.mcp')}</button>
            <button type="button" className={`w-full text-left px-4 py-3 rounded-xl transition-all duration-200 text-[11px] font-bold  active:scale-[0.98] ${activeSection === 'scheduler' ? 'bg-ops-cyan/15 text-ops-cyan shadow-glow border border-ops-cyan/30' : 'text-ops-muted hover:text-ops-text hover:bg-ops-panel/60 border border-transparent'}`} onClick={() => setActiveSection('scheduler')}>{t('settings.scheduler')}</button>
          </nav>
          <div className="flex-1 p-6 overflow-y-auto bg-ops-panel/50 relative">
            {loadError ? <div className="p-4 mb-6 rounded-md bg-red-500/10 border border-red-500/20 text-red-500 text-sm flex items-center justify-between">{loadError}<button type="button" className="px-3 py-1.5 rounded-md bg-ops-border/20 hover:bg-ops-border/30 transition-colors text-ops-text text-sm" onClick={() => void loadSettings()}>{t('common.retry')}</button></div> : null}
            {sectionError ? <div className="p-4 mb-6 rounded-md bg-red-500/10 border border-red-500/20 text-red-500 text-sm flex items-center justify-between">{sectionError}</div> : null}
            {activeSection === 'appearance' ? (
              <AppearanceSection
                language={language}
                themeMode={themeMode}
                resolvedTheme={resolvedTheme}
                onLanguageChange={setLanguage}
                onThemeModeChange={setThemeMode}
              />
            ) : loading ? (
              <div className="flex items-center justify-center h-40 text-ops-muted text-sm">{t('settings.loading')}</div>
            ) : activeSection === 'groups' ? (
              <GroupsSection
                groups={groups}
                groupForm={groupForm}
                showGroupForm={showGroupForm}
                saving={savingByDomain.groups}
                onStartCreate={startCreateGroup}
                onStartEdit={startEditGroup}
                onStartDelete={setDeletingGroup}
                onFormChange={setGroupForm}
                onCancelForm={cancelGroupForm}
                onSave={saveGroup}
              />
            ) : activeSection === 'models' ? (
              <ModelsSection
                selectedModel={selectedModel}
                modelConfigs={modelConfigs}
                modelForm={modelForm}
                showModelForm={showModelForm}
                editingModel={editingModel}
                saving={savingByDomain.models}
                testResult={modelTestResult}
                discoveredModels={discoveredModels}
                discoveringModels={discoveringModels}
                modelDiscoveryMessage={modelDiscoveryMessage}
                onStartCreate={startCreateModel}
                onStartEdit={startEditModel}
                onStartDelete={setDeletingModel}
                onFormChange={setModelForm}
                onProviderChange={handleModelProviderChange}
                onConnectionFieldChange={updateModelConnectionField}
                onCancelForm={cancelModelForm}
                onSave={saveModel}
                onSetDefault={(config) => void setDefaultModel(config)}
                onDiscoverModels={() => void discoverModels()}
                onTest={() => void testModel()}
              />
            ) : activeSection === 'sshKeys' ? (
              <SSHKeysSection
                sshKeys={sshKeys}
                sshKeyForm={sshKeyForm}
                showSSHKeyForm={showSSHKeyForm}
                editingSSHKey={editingSSHKey}
                saving={savingByDomain.sshKeys}
                onStartCreate={startCreateSSHKey}
                onStartEdit={startEditSSHKey}
                onStartDelete={setDeletingSSHKey}
                onFormChange={setSSHKeyForm}
                onCancelForm={cancelSSHKeyForm}
                onSave={saveSSHKey}
              />
            ) : activeSection === 'permissions' ? (
              <PermissionsSection
                permissionsForm={permissionsForm}
                saving={savingByDomain.permissions}
                onFormChange={setPermissionsForm}
                onSave={savePermissions}
              />
            ) : activeSection === 'skills' ? (
              <SkillsSection
                skills={skills ?? []}
                loading={skillsLoading}
                error={skillsError}
                onRetry={() => void loadSkills()}
              />
            ) : activeSection === 'scheduler' ? (
              <SchedulerSection assets={assets} />
            ) : (
              <McpSection
                servers={mcpServers}
                serverForm={mcpServerForm}
                showServerForm={showMCPServerForm}
                editingServer={editingMCPServer}
                selectedServerId={selectedMCPServerId}
                loading={mcpLoading}
                error={mcpError ?? errorByDomain.mcp}
                saving={savingByDomain.mcp}
                testResult={mcpTestResult}
                onRetry={() => void loadMCPServers()}
                onStartCreate={startCreateMCPServer}
                onStartEdit={startEditMCPServer}
                onStartDelete={setDeletingMCPServer}
                onSelectServer={setSelectedMCPServerId}
                onFormChange={setMCPServerForm}
                onCancelForm={cancelMCPServerForm}
                onSave={saveMCPServer}
                onTest={(server) => void testMCP(server)}
                onRefresh={(server) => void refreshMCP(server)}
                onSetEnabled={(server, enabled) => void setMCPEnabled(server, enabled)}
                onUpdateTool={(tool, updates) => void updateMCPToolSettings(tool, updates)}
              />
            )}
          </div>
        </div>
        {deletingGroup ? (
          <DeleteConfirmDialog
            titleId="delete-group-title"
            title={t('settings.confirmGroupDeletion')}
            message={deletingGroup.name}
            saving={savingByDomain.groups}
            onCancel={() => setDeletingGroup(null)}
            onConfirm={() => void confirmDeleteGroup()}
          />
        ) : null}
        {deletingModel ? (
          <DeleteConfirmDialog
            titleId="delete-model-title"
            title={t('settings.confirmModelDeletion')}
            message={deletingModel.isDefault ? t('settings.defaultModelCannotDelete') : deletingModel.name}
            saving={savingByDomain.models}
            confirmDisabled={deletingModel.isDefault}
            onCancel={() => setDeletingModel(null)}
            onConfirm={() => void confirmDeleteModel()}
          />
        ) : null}
        {deletingSSHKey ? (
          <DeleteConfirmDialog
            titleId="delete-ssh-key-title"
            title={t('settings.confirmSshKeyDeletion')}
            message={deletingSSHKey.name}
            saving={savingByDomain.sshKeys}
            onCancel={() => setDeletingSSHKey(null)}
            onConfirm={() => void confirmDeleteSSHKey()}
          />
        ) : null}
        {deletingMCPServer ? (
          <DeleteConfirmDialog
            titleId="delete-mcp-server-title"
            title={t('settings.confirmMcpServerDeletion')}
            message={deletingMCPServer.name}
            saving={savingByDomain.mcp}
            onCancel={() => setDeletingMCPServer(null)}
            onConfirm={() => void confirmDeleteMCPServer()}
          />
        ) : null}
      </section>
    </div>
  )
}
