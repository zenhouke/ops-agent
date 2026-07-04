import type { ModelsSectionProps } from './settingsTypes'
import { useAppearance } from '../../hooks/useAppearance'
import { modelProviderPresets } from '../../types/modelProviderPresets'

export function ModelsSection({
  selectedModel,
  modelConfigs,
  modelForm,
  showModelForm,
  editingModel,
  saving,
  testResult,
  discoveredModels,
  discoveringModels,
  modelDiscoveryMessage,
  onStartCreate,
  onStartEdit,
  onStartDelete,
  onFormChange,
  onProviderChange,
  onConnectionFieldChange,
  onCancelForm,
  onSave,
  onSetDefault,
  onDiscoverModels,
  onTest,
}: ModelsSectionProps) {
  const { t } = useAppearance()
  return (
    <div className="flex flex-col gap-8">
      <div className="flex items-center justify-between pb-4 border-b border-ops-border/20">
        <div>
          <h4 className="text-[14px] font-bold text-ops-text">{t('settings.modelsTitle')}</h4>
          <p className="text-[10px] font-medium text-ops-muted mt-1 tracking-wider opacity-60">{t('settings.activeModel')}<span className="text-ops-green">{selectedModel || t('settings.undefined')}</span></p>
        </div>
        <button type="button" className="button button-primary" onClick={onStartCreate}>{t('settings.deployNewModel')}</button>
      </div>

      {showModelForm ? (
        <form className="bg-ops-deep/40 p-6 rounded-2xl border border-ops-border/20 grid grid-cols-2 gap-5 mt-2 animate-in slide-in-from-top-4 duration-300" onSubmit={onSave}>
          <label className="flex flex-col gap-2 text-[11px] font-bold  tracking-widest text-ops-muted/70">
            {t('settings.internalName')}
            <input className="field-control" value={modelForm.name} onChange={(event) => onFormChange({ ...modelForm, name: event.target.value })} placeholder="e.g. Production Claude" required />
          </label>
          <label className="flex flex-col gap-2 text-[11px] font-bold  tracking-widest text-ops-muted/70">
            {t('settings.providerIdentity')}
            <select className="field-control" value={modelForm.provider} onChange={(event) => onProviderChange(event.target.value)}>
              {modelProviderPresets.map((preset) => (
                <option key={preset.provider} value={preset.provider}>{preset.label}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-2 text-[11px] font-bold  tracking-widest text-ops-muted/70 col-span-2">
            {t('settings.endpointBaseUrl')}
            <input className="field-control font-mono" value={modelForm.baseUrl} onChange={(event) => onConnectionFieldChange({ baseUrl: event.target.value })} placeholder="https://api.anthropic.com" required />
          </label>
          <label className="flex flex-col gap-2 text-[11px] font-bold  tracking-widest text-ops-muted/70 col-span-2">
            {t('settings.authorizationToken')}
            <input className="field-control font-mono" type="password" value={modelForm.apiKey} onChange={(event) => onConnectionFieldChange({ apiKey: event.target.value })} placeholder={editingModel ? t('settings.unmodified') : 'sk-••••••••••••••••'} required={!editingModel} />
          </label>
          <div className="flex flex-col gap-3 col-span-2">
            <div className="flex items-end gap-3">
              <label className="flex flex-1 flex-col gap-2 text-[11px] font-bold  tracking-widest text-ops-muted/70">
                {t('settings.targetModelIdentifier')}
                <select className="field-control font-mono" value={modelForm.modelName} onChange={(event) => onFormChange({ ...modelForm, modelName: event.target.value })} required disabled={discoveredModels.length === 0}>
                  {discoveredModels.length === 0 ? <option value="">Discover models first</option> : null}
                  {discoveredModels.map((modelName) => (
                    <option key={modelName} value={modelName}>{modelName}</option>
                  ))}
                </select>
              </label>
              <button type="button" className="button px-6 h-[42px]" onClick={onDiscoverModels} disabled={saving || discoveringModels || !modelForm.baseUrl.trim() || !modelForm.apiKey.trim()}>
                {discoveringModels ? t('settings.processing') : 'Discover models'}
              </button>
            </div>
            {modelDiscoveryMessage ? <div className="text-[11px] font-mono text-ops-muted/80 break-all">{modelDiscoveryMessage}</div> : null}
          </div>
          <label className="flex flex-col gap-2 text-[11px] font-bold  tracking-widest text-ops-muted/70">
            {t('settings.requestTimeout')}
            <input className="field-control font-mono" type="number" min="1" value={modelForm.timeoutSeconds} onChange={(event) => onFormChange({ ...modelForm, timeoutSeconds: event.target.value })} required />
          </label>
          <label className="flex flex-col gap-2 text-[11px] font-bold  tracking-widest text-ops-muted/70">
            {t('settings.temperature')}
            <input className="field-control font-mono" type="number" step="0.1" value={modelForm.temperature} onChange={(event) => onFormChange({ ...modelForm, temperature: event.target.value })} required />
          </label>
          <label className="flex flex-col gap-2 text-[11px] font-bold  tracking-widest text-ops-muted/70 col-span-2 sm:col-span-1">
            {t('settings.maxTokenOutput')}
            <input className="field-control font-mono" type="number" min="1" value={modelForm.maxTokens} onChange={(event) => onFormChange({ ...modelForm, maxTokens: event.target.value })} required />
          </label>
          <label className="flex items-center gap-3 text-[11px] font-bold  tracking-widest text-ops-text col-span-2 mt-2">
            <input type="checkbox" className="accent-ops-green w-4 h-4 rounded-md" checked={modelForm.isDefault} disabled={editingModel?.isDefault} onChange={(event) => onFormChange({ ...modelForm, isDefault: event.target.checked })} />
            {editingModel?.isDefault ? t('settings.primaryDefaultDeployment') : t('settings.setAsPrimaryDefault')}
          </label>
          <label className="flex flex-col gap-2 text-[11px] font-bold  tracking-widest text-ops-muted/70 col-span-2">
            {t('settings.instanceDescription')}
            <textarea className="field-control min-h-[80px]" value={modelForm.description} onChange={(event) => onFormChange({ ...modelForm, description: event.target.value })} placeholder={t('settings.deploymentDetailsPlaceholder')} rows={3} />
          </label>
          {testResult ? <div className="col-span-2 p-4 text-[11px] font-mono text-ops-green bg-ops-green/10 border border-ops-green/20 rounded-xl break-all animate-in fade-in duration-300">{testResult}</div> : null}
          <div className="flex items-center justify-between gap-3 mt-4 pt-6 border-t border-ops-border/20 col-span-2">
            <button type="button" className="button px-6" onClick={onTest} disabled={saving || !modelForm.apiKey.trim() || !modelForm.modelName.trim()} title={editingModel && !modelForm.apiKey.trim() ? t('settings.enterApiKeyToTest') : undefined}>{t('settings.pingEndpoint')}</button>
            <div className="flex items-center gap-3">
              <button type="button" className="button px-6" onClick={onCancelForm}>{t('common.cancel')}</button>
              <button type="submit" className="button button-primary px-8" disabled={saving || !modelForm.modelName.trim()}>{saving ? t('settings.processing') : t('settings.authorize')}</button>
            </div>
          </div>
        </form>
      ) : null}

      {modelConfigs.length === 0 ? (
        <div className="flex flex-col gap-3">
          <div className="text-center py-6 text-ops-muted text-sm bg-ops-panel/20 rounded-lg border border-ops-border/10 border-dashed mb-2">
            {t('settings.noModelConfigs')}
          </div>
          {selectedModel && (
            <article className="flex items-center justify-between p-5 rounded-2xl bg-ops-panel/40 border border-ops-green/30 bg-ops-green/5 shadow-sm">
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center gap-3">
                  <strong className="text-[13px] font-bold text-ops-text tracking-tight">{t('settings.environmentDefault')}</strong>
                  <span className="px-2 py-0.5 text-[10px] font-bold  tracking-widest rounded-md text-ops-green bg-ops-green/10 border border-ops-green/20 shadow-glow">{t('settings.active')}</span>
                </div>
                <span className="text-[10px] text-ops-muted font-bold  tracking-[0.1em] opacity-60">{t('settings.systemFallback')} / {selectedModel}</span>
              </div>
              <div className="text-[10px] text-ops-muted italic">{t('settings.managedViaEnv')}</div>
            </article>
          )}
        </div>
      ) : null}
      <div className="flex flex-col gap-3">
        {modelConfigs.map((config) => (
          <article key={config.id} className="flex items-center justify-between p-5 rounded-2xl bg-ops-panel/40 border border-ops-border/20 hover:border-ops-green/30 hover:bg-ops-panel/60 transition-all duration-300 group shadow-sm">
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center gap-3">
                <strong className="text-[13px] font-bold text-ops-text tracking-tight">{config.name}</strong>
                {config.isDefault ? <span className="px-2 py-0.5 text-[10px] font-bold  tracking-widest rounded-md text-ops-emerald bg-ops-emerald/10 border border-ops-emerald/20 shadow-glow">{t('settings.primary')}</span> : null}
              </div>
              <span className="text-[10px] text-ops-muted font-bold  tracking-[0.1em] opacity-60">{config.provider} / {config.modelName} / {config.apiKeyMasked}</span>
            </div>
            <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-all duration-200">
              {!config.isDefault ? <button type="button" className="button h-8 px-4 text-[10px]" onClick={() => onSetDefault(config)} disabled={saving}>{t('settings.setPrimary')}</button> : null}
              <button type="button" className="button h-8 px-4 text-[10px]" onClick={() => onStartEdit(config)}>{t('common.edit')}</button>
              <button type="button" className="button button-danger h-8 px-4 text-[10px]" onClick={() => onStartDelete(config)} disabled={config.isDefault} title={config.isDefault ? t('settings.setAnotherPrimaryFirst') : undefined}>{t('common.delete')}</button>
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}
