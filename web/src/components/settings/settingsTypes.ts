import type { FormEvent } from 'react'
import type { Language } from '../../i18n/translations'
import type { ResolvedTheme, ThemeMode } from '../../hooks/useAppearance'
import type { AssetGroup, MCPApprovalPolicy, MCPServer, MCPTool, MCPTransport, ModelConfig, SSHKey, SkillPackage } from '../../types/ops'

export type SettingsSection = 'appearance' | 'models' | 'permissions'

export type GroupForm = {
  name: string
  description: string
}

export type ModelForm = {
  name: string
  provider: string
  baseUrl: string
  apiKey: string
  modelName: string
  isDefault: boolean
  timeoutSeconds: string
  temperature: string
  maxTokens: string
  description: string
  providerOptions: Record<string, unknown>
}

export type SSHKeyForm = {
  name: string
  publicKey: string
  privateKey: string
  passphrase: string
}

export type PermissionsForm = {
  allow: string[]
  deny: string[]
  allowInput: string
  denyInput: string
}

export type MCPServerForm = {
  name: string
  transport: MCPTransport
  command: string
  args: string
  env: string
  url: string
  headers: string
  timeoutSeconds: string
}

export type SettingsDialogProps = {
  selectedModel: string
  onSelectedModelChange: (model: string) => void
  onModelOptionsChange: (modelOptions: string[]) => void
  onClose: () => void
}

export type AppearanceSectionProps = {
  language: Language
  themeMode: ThemeMode
  resolvedTheme: ResolvedTheme
  onLanguageChange: (language: Language) => void
  onThemeModeChange: (themeMode: ThemeMode) => void
}

export type GroupsSectionProps = {
  groups: AssetGroup[]
  groupForm: GroupForm
  showGroupForm: boolean
  saving: boolean
  onStartCreate: () => void
  onStartEdit: (group: AssetGroup) => void
  onStartDelete: (group: AssetGroup) => void
  onFormChange: (form: GroupForm) => void
  onCancelForm: () => void
  onSave: (event: FormEvent<HTMLFormElement>) => void
}

export type ModelsSectionProps = {
  selectedModel: string
  modelConfigs: ModelConfig[]
  modelForm: ModelForm
  showModelForm: boolean
  editingModel: ModelConfig | null
  saving: boolean
  testResult: string | null
  discoveredModels: string[]
  discoveringModels: boolean
  modelDiscoveryMessage: string | null
  onStartCreate: () => void
  onStartEdit: (config: ModelConfig) => void
  onStartDelete: (config: ModelConfig) => void
  onFormChange: (form: ModelForm) => void
  onProviderChange: (provider: string) => void
  onConnectionFieldChange: (updates: Partial<Pick<ModelForm, 'baseUrl' | 'apiKey'>>) => void
  onCancelForm: () => void
  onSave: (event: FormEvent<HTMLFormElement>) => void
  onSetDefault: (config: ModelConfig) => void
  onDiscoverModels: () => void
  onTest: () => void
}

export type SSHKeysSectionProps = {
  sshKeys: SSHKey[]
  sshKeyForm: SSHKeyForm
  showSSHKeyForm: boolean
  editingSSHKey: SSHKey | null
  saving: boolean
  onStartCreate: () => void
  onStartEdit: (sshKey: SSHKey) => void
  onStartDelete: (sshKey: SSHKey) => void
  onFormChange: (form: SSHKeyForm) => void
  onCancelForm: () => void
  onSave: (event: FormEvent<HTMLFormElement>) => void
}

export type PermissionsSectionProps = {
  permissionsForm: PermissionsForm
  saving: boolean
  onFormChange: (form: PermissionsForm) => void
  onSave: (event: FormEvent<HTMLFormElement>) => void
}

export type SkillsSectionProps = {
  skills: SkillPackage[]
  loading: boolean
  error: string | null
  onRetry: () => void
}

export type MCPSectionProps = {
  servers: MCPServer[]
  serverForm: MCPServerForm
  showServerForm: boolean
  editingServer: MCPServer | null
  selectedServerId: string | null
  loading: boolean
  error: string | null
  saving: boolean
  testResult: string | null
  onRetry: () => void
  onStartCreate: () => void
  onStartEdit: (server: MCPServer) => void
  onStartDelete: (server: MCPServer) => void
  onSelectServer: (serverId: string) => void
  onFormChange: (form: MCPServerForm) => void
  onCancelForm: () => void
  onSave: (event: FormEvent<HTMLFormElement>) => void
  onTest: (server: MCPServer) => void
  onRefresh: (server: MCPServer) => void
  onSetEnabled: (server: MCPServer, enabled: boolean) => void
  onUpdateTool: (tool: MCPTool, updates: { enabled?: boolean; approvalPolicy?: MCPApprovalPolicy }) => void
}
