import { type FormEvent, useEffect, useState } from 'react'
import { getApprovalPolicy, updateApprovalPolicy } from '../../api'
import { useAppearance } from '../../hooks/useAppearance'
import { AppearanceSection } from './AppearanceSection'
import { DeleteConfirmDialog } from './DeleteConfirmDialog'
import { ModelsSection } from './ModelsSection'
import { PermissionsSection } from './PermissionsSection'
import { PromptsSection } from './PromptsSection'
import { JumpServerSection } from './JumpServerSection'
import type { PermissionsForm, SettingsDialogProps, SettingsSection } from './settingsTypes'
import { useModelSettings } from './useModelSettings'
import { usePromptSettings } from './usePromptSettings'

const emptyPermissionsForm: PermissionsForm = {
  allow: [],
  deny: [],
  allowInput: '',
  denyInput: '',
}

export function SettingsDialog({ selectedModel, onSelectedModelChange, onModelOptionsChange, onClose }: SettingsDialogProps) {
  const { language, themeMode, resolvedTheme, setLanguage, setThemeMode, t } = useAppearance()
  const model = useModelSettings({ onModelOptionsChange, onSelectedModelChange })
  const prompts = usePromptSettings()
  const [activeSection, setActiveSection] = useState<SettingsSection>('appearance')
  const [permissionsForm, setPermissionsForm] = useState(emptyPermissionsForm)
  const [permissionsLoading, setPermissionsLoading] = useState(true)
  const [permissionsSaving, setPermissionsSaving] = useState(false)
  const [permissionsError, setPermissionsError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    void getApprovalPolicy()
      .then((policy) => {
        if (!active) return
        setPermissionsForm({
          allow: policy.permissions.allow,
          deny: policy.permissions.deny,
          allowInput: '',
          denyInput: '',
        })
      })
      .catch((cause: unknown) => {
        if (active) setPermissionsError(cause instanceof Error ? cause.message : t('settings.permissionsLoadFailed'))
      })
      .finally(() => {
        if (active) setPermissionsLoading(false)
      })
    return () => { active = false }
  }, [t])

  const savePermissions = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setPermissionsSaving(true)
    setPermissionsError(null)
    try {
      await updateApprovalPolicy({ permissions: { allow: permissionsForm.allow, deny: permissionsForm.deny } })
      setPermissionsForm((current) => ({ ...current, allowInput: '', denyInput: '' }))
    } catch (cause) {
      setPermissionsError(cause instanceof Error ? cause.message : t('settings.permissionsSaveFailed'))
    } finally {
      setPermissionsSaving(false)
    }
  }

  const sections: SettingsSection[] = ['appearance', 'models', 'prompts', 'jumpserver', 'permissions']
  const sectionError = activeSection === 'models' ? model.error : activeSection === 'prompts' ? prompts.error : activeSection === 'permissions' ? permissionsError : null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ops-bg/70 backdrop-blur-sm" role="presentation">
      <section className="flex h-[640px] max-h-[90vh] w-[880px] max-w-[95vw] flex-col overflow-hidden rounded-lg border border-ops-border/45 bg-ops-panel shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="settings-title">
        <header className="flex h-16 shrink-0 items-center justify-between border-b border-ops-border/25 bg-ops-deep/55 px-5">
          <div>
            <h3 id="settings-title" className="text-[15px] font-semibold text-ops-text">{t('settings.title')}</h3>
            <p className="mt-0.5 text-[10px] text-ops-muted/65">{t('settings.description')}</p>
          </div>
          <button type="button" className="desktop-icon-button" onClick={onClose} aria-label={t('common.close')}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M18 6 6 18M6 6l12 12" /></svg>
          </button>
        </header>
        <div className="flex min-h-0 flex-1">
          <nav className="w-[190px] shrink-0 border-r border-ops-border/25 bg-ops-deep/30 p-2" aria-label={t('settings.navigation')}>
            {sections.map((section) => (
              <button
                key={section}
                type="button"
                className={`mb-0.5 w-full rounded px-3 py-2.5 text-left text-[11px] font-medium transition-all duration-200 active:scale-[0.99] ${activeSection === section ? 'bg-ops-text text-ops-bg' : 'text-ops-muted hover:bg-ops-panel hover:text-ops-text'}`}
                onClick={() => setActiveSection(section)}
              >
                {t(`settings.${section}`)}
              </button>
            ))}
          </nav>
          <main className="min-w-0 flex-1 overflow-y-auto bg-ops-panel/50 p-6">
            {sectionError ? <div className="mb-5 border border-ops-danger/30 bg-ops-danger/5 px-3 py-2 text-xs text-ops-danger">{sectionError}</div> : null}
            {activeSection === 'appearance' ? (
              <AppearanceSection language={language} themeMode={themeMode} resolvedTheme={resolvedTheme} onLanguageChange={setLanguage} onThemeModeChange={setThemeMode} />
            ) : activeSection === 'models' ? (
              <ModelsSection
                selectedModel={selectedModel}
                modelConfigs={model.modelConfigs}
                modelForm={model.modelForm}
                showModelForm={model.showModelForm}
                editingModel={model.editingModel}
                saving={model.saving}
                testResult={model.testResult}
                discoveredModels={model.discoveredModels}
                discoveringModels={model.discoveringModels}
                modelDiscoveryMessage={model.discoveryMessage}
                onStartCreate={model.startCreate}
                onStartEdit={model.startEdit}
                onStartDelete={model.setDeletingModel}
                onFormChange={model.setModelForm}
                onProviderChange={model.handleProviderChange}
                onConnectionFieldChange={model.updateConnectionField}
                onCancelForm={model.resetForm}
                onSave={model.save}
                onSetDefault={(config) => void model.setDefault(config)}
                onDiscoverModels={() => void model.discover()}
                onTest={() => void model.test()}
              />
            ) : activeSection === 'prompts' ? (
              prompts.loading ? (
                <div className="py-16 text-center text-xs text-ops-muted">{t('settings.loading')}</div>
              ) : !prompts.settings || !prompts.overrides ? (
                <div className="flex flex-col items-center gap-3 py-16 text-xs text-ops-muted">
                  <span>{prompts.error}</span>
                  <button type="button" className="button" onClick={() => void prompts.load()}>{t('common.retry')}</button>
                </div>
              ) : (
                <PromptsSection
                  key={prompts.settings.revision}
                  settings={prompts.settings}
                  overrides={prompts.overrides}
                  saving={prompts.saving}
                  saved={prompts.saved}
                  onChange={prompts.setOverrides}
                  onSave={() => void prompts.save()}
                  onReset={() => void prompts.reset()}
                />
              )
            ) : activeSection === 'jumpserver' ? (
              <JumpServerSection />
            ) : permissionsLoading ? (
              <div className="py-16 text-center text-xs text-ops-muted">{t('settings.loading')}</div>
            ) : (
              <PermissionsSection permissionsForm={permissionsForm} saving={permissionsSaving} onFormChange={setPermissionsForm} onSave={savePermissions} />
            )}
          </main>
        </div>
        {model.deletingModel ? (
          <DeleteConfirmDialog
            titleId="delete-model-title"
            title={t('settings.confirmModelDeletion')}
            message={model.deletingModel.isDefault ? t('settings.defaultModelCannotDelete') : model.deletingModel.name}
            saving={model.saving}
            confirmDisabled={model.deletingModel.isDefault}
            onCancel={() => model.setDeletingModel(null)}
            onConfirm={() => void model.confirmDelete()}
          />
        ) : null}
      </section>
    </div>
  )
}
