import { type FormEvent, useEffect, useState } from 'react'

import {
  createGroup,
  createSSHKey,
  deleteGroup,
  deleteSSHKey,
  getApprovalPolicy,
  getGroups,
  getSSHKeys,
  updateApprovalPolicy,
  updateGroup,
  updateSSHKey,
} from '../../api'
import { useAppearance } from '../../hooks/useAppearance'
import { useSkillPackages } from '../../hooks/useSkillPackages'
import type { AssetGroup, SSHKey } from '../../types/ops'
import { AppearanceSection } from './AppearanceSection'
import { DeleteConfirmDialog } from './DeleteConfirmDialog'
import { GroupsSection } from './GroupsSection'
import { McpSection } from './McpSection'
import { ModelsSection } from './ModelsSection'
import { PermissionsSection } from './PermissionsSection'
import { PluginsSection } from './PluginsSection'
import { SchedulerSection } from './SchedulerSection'
import type {
  GroupForm,
  PermissionsForm,
  SettingsDialogProps,
  SettingsSection,
  SSHKeyForm,
} from './settingsTypes'
import { SkillsSection } from './SkillsSection'
import { SSHKeysSection } from './SSHKeysSection'
import { useMcpSettings } from './useMcpSettings'
import { useModelSettings } from './useModelSettings'

const emptyGroupForm: GroupForm = { name: '', description: '' }
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

type OperationDomain = 'groups' | 'sshKeys' | 'permissions'
const emptySaving: Record<OperationDomain, boolean> = {
  groups: false,
  sshKeys: false,
  permissions: false,
}
const emptyErrors: Record<OperationDomain, string | null> = {
  groups: null,
  sshKeys: null,
  permissions: null,
}

export function SettingsDialog({
  initialGroups,
  selectedModel,
  sshKeys: initialSSHKeys,
  assets,
  onSelectedModelChange,
  onGroupsChange,
  onModelOptionsChange,
  onSSHKeysChange,
  onClose,
}: SettingsDialogProps) {
  const { language, themeMode, resolvedTheme, setLanguage, setThemeMode, t } = useAppearance()
  const { skillPackages: skills, loading: skillsLoading, error: skillsError, loadSkillPackages } = useSkillPackages()
  const model = useModelSettings({ onModelOptionsChange, onSelectedModelChange })
  const mcp = useMcpSettings()
  const [activeSection, setActiveSection] = useState<SettingsSection>('appearance')
  const [groups, setGroups] = useState(initialGroups)
  const [sshKeys, setSSHKeys] = useState(initialSSHKeys)
  const [permissionsForm, setPermissionsForm] = useState(emptyPermissionsForm)
  const [groupForm, setGroupForm] = useState(emptyGroupForm)
  const [sshKeyForm, setSSHKeyForm] = useState(emptySSHKeyForm)
  const [showGroupForm, setShowGroupForm] = useState(false)
  const [showSSHKeyForm, setShowSSHKeyForm] = useState(false)
  const [editingGroup, setEditingGroup] = useState<AssetGroup | null>(null)
  const [deletingGroup, setDeletingGroup] = useState<AssetGroup | null>(null)
  const [editingSSHKey, setEditingSSHKey] = useState<SSHKey | null>(null)
  const [deletingSSHKey, setDeletingSSHKey] = useState<SSHKey | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saving, setSaving] = useState(emptySaving)
  const [errors, setErrors] = useState(emptyErrors)

  const loadSettings = async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const [nextGroups, nextSSHKeys, policy] = await Promise.all([
        getGroups(),
        getSSHKeys(),
        getApprovalPolicy(),
      ])
      setGroups(nextGroups)
      setSSHKeys(nextSSHKeys)
      onGroupsChange(nextGroups)
      onSSHKeysChange(nextSSHKeys)
      setPermissionsForm({
        allow: policy.permissions.allow,
        deny: policy.permissions.deny,
        allowInput: '',
        denyInput: '',
      })
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : 'Failed to load settings')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadSettings()
    void loadSkillPackages(true)
  }, [])

  const runSaving = async (
    domain: OperationDomain,
    action: () => Promise<void>,
    fallback: string,
  ) => {
    setSaving((current) => ({ ...current, [domain]: true }))
    setErrors((current) => ({ ...current, [domain]: null }))
    try {
      await action()
    } catch (error) {
      setErrors((current) => ({
        ...current,
        [domain]: error instanceof Error ? error.message : fallback,
      }))
    } finally {
      setSaving((current) => ({ ...current, [domain]: false }))
    }
  }

  const resetGroupForm = () => {
    setEditingGroup(null)
    setShowGroupForm(false)
    setGroupForm(emptyGroupForm)
  }

  const saveGroup = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    await runSaving('groups', async () => {
      const payload = {
        name: groupForm.name.trim(),
        description: groupForm.description.trim(),
      }
      const saved = editingGroup
        ? await updateGroup(editingGroup.id, payload)
        : await createGroup(payload)
      const next = editingGroup
        ? groups.map((group) => group.id === saved.id ? saved : group)
        : [saved, ...groups]
      setGroups(next)
      onGroupsChange(next)
      resetGroupForm()
    }, 'Failed to save group')
  }

  const confirmDeleteGroup = async () => {
    if (!deletingGroup) return
    await runSaving('groups', async () => {
      await deleteGroup(deletingGroup.id)
      const next = groups.filter((group) => group.id !== deletingGroup.id)
      setGroups(next)
      onGroupsChange(next)
      setDeletingGroup(null)
    }, 'Failed to delete group')
  }

  const resetSSHKeyForm = () => {
    setEditingSSHKey(null)
    setShowSSHKeyForm(false)
    setSSHKeyForm(emptySSHKeyForm)
  }

  const saveSSHKey = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    await runSaving('sshKeys', async () => {
      const payload = {
        name: sshKeyForm.name.trim(),
        public_key: sshKeyForm.publicKey.trim(),
        private_key: sshKeyForm.privateKey.trim() || undefined,
        passphrase: sshKeyForm.passphrase.trim() || undefined,
      }
      const saved = editingSSHKey
        ? await updateSSHKey(editingSSHKey.id, payload)
        : await createSSHKey({ ...payload, private_key: sshKeyForm.privateKey.trim() })
      const next = editingSSHKey
        ? sshKeys.map((key) => key.id === saved.id ? saved : key)
        : [saved, ...sshKeys]
      setSSHKeys(next)
      onSSHKeysChange(next)
      resetSSHKeyForm()
    }, 'Failed to save SSH key')
  }

  const confirmDeleteSSHKey = async () => {
    if (!deletingSSHKey) return
    await runSaving('sshKeys', async () => {
      await deleteSSHKey(deletingSSHKey.id)
      const next = sshKeys.filter((key) => key.id !== deletingSSHKey.id)
      setSSHKeys(next)
      onSSHKeysChange(next)
      setDeletingSSHKey(null)
    }, 'Failed to delete SSH key')
  }

  const savePermissions = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    await runSaving('permissions', async () => {
      await updateApprovalPolicy({
        permissions: { allow: permissionsForm.allow, deny: permissionsForm.deny },
      })
      setPermissionsForm((current) => ({ ...current, allowInput: '', denyInput: '' }))
    }, 'Failed to save permissions')
  }

  const sectionError = activeSection === 'groups'
    ? errors.groups
    : activeSection === 'models'
      ? model.error
      : activeSection === 'sshKeys'
        ? errors.sshKeys
        : activeSection === 'permissions'
          ? errors.permissions
          : null
  const sections: SettingsSection[] = [
    'appearance',
    'groups',
    'models',
    'sshKeys',
    'permissions',
    'skills',
    'plugins',
    'mcp',
    'scheduler',
  ]

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ops-bg/60 backdrop-blur-md animate-in fade-in duration-300" role="presentation">
      <section className="w-[880px] max-w-[95vw] h-[640px] max-h-[90vh] bg-ops-panel/90 border border-ops-border/40 rounded-2xl shadow-2xl flex flex-col overflow-hidden backdrop-blur-xl animate-in zoom-in-95 duration-300" role="dialog" aria-modal="true" aria-labelledby="settings-title">
        <header className="flex items-center justify-between p-6 border-b border-ops-border/20 bg-ops-panel shrink-0">
          <div>
            <h3 id="settings-title" className="text-[16px] font-bold text-ops-cyan">{t('settings.title')}</h3>
            <p className="text-[11px] font-medium text-ops-muted mt-1 tracking-wider opacity-60">{t('settings.description')}</p>
          </div>
          <button type="button" className="h-8 px-4 text-[11px] font-bold tracking-widest rounded-lg transition-all text-ops-muted hover:text-ops-text hover:bg-ops-border/30 active:scale-95" onClick={onClose}>{t('common.close')}</button>
        </header>
        <div className="flex flex-1 flex-col overflow-hidden md:flex-row">
          <nav className="flex max-h-28 shrink-0 gap-2 overflow-x-auto overflow-y-hidden border-b border-ops-border/20 bg-ops-deep/40 p-3 md:max-h-none md:w-[220px] md:flex-col md:overflow-x-hidden md:overflow-y-auto md:border-b-0 md:border-r md:p-4" aria-label={t('settings.navigation')}>
            {sections.map((section) => (
              <button key={section} type="button" className={`w-full text-left px-4 py-3 rounded-xl transition-all text-[11px] font-bold active:scale-[0.98] ${activeSection === section ? 'bg-ops-cyan/15 text-ops-cyan shadow-glow border border-ops-cyan/30' : 'text-ops-muted hover:text-ops-text hover:bg-ops-panel/60 border border-transparent'}`} onClick={() => setActiveSection(section)}>
                {t(`settings.${section}`)}
              </button>
            ))}
          </nav>
          <main className="flex-1 p-6 overflow-y-auto bg-ops-panel/50 relative">
            {loadError ? <div className="p-4 mb-6 rounded-md bg-red-500/10 border border-red-500/20 text-red-500 text-sm flex items-center justify-between">{loadError}<button type="button" className="px-3 py-1.5 rounded-md bg-ops-border/20 hover:bg-ops-border/30 text-ops-text text-sm" onClick={() => void loadSettings()}>{t('common.retry')}</button></div> : null}
            {sectionError ? <div className="p-4 mb-6 rounded-md bg-red-500/10 border border-red-500/20 text-red-500 text-sm">{sectionError}</div> : null}
            {activeSection === 'appearance' ? (
              <AppearanceSection language={language} themeMode={themeMode} resolvedTheme={resolvedTheme} onLanguageChange={setLanguage} onThemeModeChange={setThemeMode} />
            ) : loading ? (
              <div className="flex items-center justify-center h-40 text-ops-muted text-sm">{t('settings.loading')}</div>
            ) : activeSection === 'groups' ? (
              <GroupsSection
                groups={groups} groupForm={groupForm} showGroupForm={showGroupForm}
                saving={saving.groups} onFormChange={setGroupForm} onCancelForm={resetGroupForm}
                onSave={saveGroup} onStartDelete={setDeletingGroup}
                onStartCreate={() => { setEditingGroup(null); setDeletingGroup(null); setGroupForm(emptyGroupForm); setShowGroupForm(true) }}
                onStartEdit={(group) => { setEditingGroup(group); setDeletingGroup(null); setGroupForm({ name: group.name, description: group.description }); setShowGroupForm(true) }}
              />
            ) : activeSection === 'models' ? (
              <ModelsSection
                selectedModel={selectedModel} modelConfigs={model.modelConfigs}
                modelForm={model.modelForm} showModelForm={model.showModelForm}
                editingModel={model.editingModel} saving={model.saving}
                testResult={model.testResult} discoveredModels={model.discoveredModels}
                discoveringModels={model.discoveringModels} modelDiscoveryMessage={model.discoveryMessage}
                onStartCreate={model.startCreate} onStartEdit={model.startEdit}
                onStartDelete={model.setDeletingModel} onFormChange={model.setModelForm}
                onProviderChange={model.handleProviderChange}
                onConnectionFieldChange={model.updateConnectionField}
                onCancelForm={model.resetForm} onSave={model.save}
                onSetDefault={(config) => void model.setDefault(config)}
                onDiscoverModels={() => void model.discover()} onTest={() => void model.test()}
              />
            ) : activeSection === 'sshKeys' ? (
              <SSHKeysSection
                sshKeys={sshKeys} sshKeyForm={sshKeyForm} showSSHKeyForm={showSSHKeyForm}
                editingSSHKey={editingSSHKey} saving={saving.sshKeys}
                onFormChange={setSSHKeyForm} onCancelForm={resetSSHKeyForm}
                onSave={saveSSHKey} onStartDelete={setDeletingSSHKey}
                onStartCreate={() => { setEditingSSHKey(null); setDeletingSSHKey(null); setSSHKeyForm(emptySSHKeyForm); setShowSSHKeyForm(true) }}
                onStartEdit={(key) => { setEditingSSHKey(key); setDeletingSSHKey(null); setSSHKeyForm({ name: key.name, publicKey: key.publicKey, privateKey: '', passphrase: '' }); setShowSSHKeyForm(true) }}
              />
            ) : activeSection === 'permissions' ? (
              <PermissionsSection permissionsForm={permissionsForm} saving={saving.permissions} onFormChange={setPermissionsForm} onSave={savePermissions} />
            ) : activeSection === 'skills' ? (
              <SkillsSection skills={skills ?? []} loading={skillsLoading} error={skillsError} onRetry={() => void loadSkillPackages(true)} />
            ) : activeSection === 'plugins' ? (
              <PluginsSection />
            ) : activeSection === 'scheduler' ? (
              <SchedulerSection assets={assets} />
            ) : (
              <McpSection
                servers={mcp.servers} serverForm={mcp.serverForm}
                showServerForm={mcp.showServerForm} editingServer={mcp.editingServer}
                selectedServerId={mcp.selectedServerId} loading={mcp.loading}
                error={mcp.error} saving={mcp.saving} testResult={mcp.testResult}
                onRetry={() => void mcp.load()} onStartCreate={mcp.startCreate}
                onStartEdit={mcp.startEdit} onStartDelete={mcp.setDeletingServer}
                onSelectServer={mcp.setSelectedServerId} onFormChange={mcp.setServerForm}
                onCancelForm={mcp.resetForm} onSave={mcp.save}
                onTest={(server) => void mcp.test(server)}
                onRefresh={(server) => void mcp.refresh(server)}
                onSetEnabled={(server, enabled) => void mcp.setEnabled(server, enabled)}
                onUpdateTool={(tool, updates) => void mcp.updateTool(tool, updates)}
              />
            )}
          </main>
        </div>
        {deletingGroup ? <DeleteConfirmDialog titleId="delete-group-title" title={t('settings.confirmGroupDeletion')} message={deletingGroup.name} saving={saving.groups} onCancel={() => setDeletingGroup(null)} onConfirm={() => void confirmDeleteGroup()} /> : null}
        {model.deletingModel ? <DeleteConfirmDialog titleId="delete-model-title" title={t('settings.confirmModelDeletion')} message={model.deletingModel.isDefault ? t('settings.defaultModelCannotDelete') : model.deletingModel.name} saving={model.saving} confirmDisabled={model.deletingModel.isDefault} onCancel={() => model.setDeletingModel(null)} onConfirm={() => void model.confirmDelete()} /> : null}
        {deletingSSHKey ? <DeleteConfirmDialog titleId="delete-ssh-key-title" title={t('settings.confirmSshKeyDeletion')} message={deletingSSHKey.name} saving={saving.sshKeys} onCancel={() => setDeletingSSHKey(null)} onConfirm={() => void confirmDeleteSSHKey()} /> : null}
        {mcp.deletingServer ? <DeleteConfirmDialog titleId="delete-mcp-server-title" title={t('settings.confirmMcpServerDeletion')} message={mcp.deletingServer.name} saving={mcp.saving} onCancel={() => mcp.setDeletingServer(null)} onConfirm={() => void mcp.confirmDelete()} /> : null}
      </section>
    </div>
  )
}
