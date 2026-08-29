import { useState } from 'react'
import type { PromptOverrides, PromptSettingKey, PromptSettings } from '../../api'
import { useAppearance } from '../../hooks/useAppearance'

const promptKeys: PromptSettingKey[] = [
  'agentBehavior',
  'incidentResponse',
  'knowledgeExtraction',
  'memoryUsage',
  'organizationRules',
]

const promptTranslationKeys = {
  agentBehavior: { title: 'settings.prompt.agentBehavior.title', description: 'settings.prompt.agentBehavior.description' },
  incidentResponse: { title: 'settings.prompt.incidentResponse.title', description: 'settings.prompt.incidentResponse.description' },
  knowledgeExtraction: { title: 'settings.prompt.knowledgeExtraction.title', description: 'settings.prompt.knowledgeExtraction.description' },
  memoryUsage: { title: 'settings.prompt.memoryUsage.title', description: 'settings.prompt.memoryUsage.description' },
  organizationRules: { title: 'settings.prompt.organizationRules.title', description: 'settings.prompt.organizationRules.description' },
} as const

type PromptsSectionProps = {
  settings: PromptSettings
  overrides: PromptOverrides
  saving: boolean
  saved: boolean
  onChange: (overrides: PromptOverrides) => void
  onSave: () => void
  onReset: () => void
}

export function PromptsSection({ settings, overrides, saving, saved, onChange, onSave, onReset }: PromptsSectionProps) {
  const { t } = useAppearance()
  const [previewKey, setPreviewKey] = useState<PromptSettingKey | null>(null)
  const [customModes, setCustomModes] = useState<Record<PromptSettingKey, boolean>>(() => ({
    agentBehavior: Boolean(overrides.agentBehavior),
    incidentResponse: Boolean(overrides.incidentResponse),
    knowledgeExtraction: Boolean(overrides.knowledgeExtraction),
    memoryUsage: Boolean(overrides.memoryUsage),
    organizationRules: Boolean(overrides.organizationRules),
  }))

  const setCustomMode = (key: PromptSettingKey, custom: boolean) => {
    setCustomModes((current) => ({ ...current, [key]: custom }))
    onChange({ ...overrides, [key]: custom ? (overrides[key] || settings.defaults[key]) : '' })
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="border-b border-ops-border/20 pb-4">
        <h4 className="text-[14px] font-bold text-ops-text">{t('settings.promptsTitle')}</h4>
        <p className="mt-1 text-[10px] font-medium tracking-wider text-ops-muted opacity-70">{t('settings.promptsDescription')}</p>
      </header>

      <section className="rounded-xl border border-ops-warning/25 bg-ops-warning/5 p-4">
        <div className="text-[11px] font-bold text-ops-warning">{t('settings.immutableSafety')}</div>
        <p className="mt-1 text-[10px] leading-5 text-ops-muted">{settings.immutableSafetySummary}</p>
      </section>

      <div className="flex flex-col gap-4">
        {promptKeys.map((key) => {
          const custom = customModes[key]
          const effective = custom ? overrides[key] : settings.defaults[key]
          return (
            <section key={key} className="rounded-xl border border-ops-border/25 bg-ops-deep/35 p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <h5 className="text-[12px] font-bold text-ops-text">{t(promptTranslationKeys[key].title)}</h5>
                  <p className="mt-1 text-[10px] leading-4 text-ops-muted">{t(promptTranslationKeys[key].description)}</p>
                </div>
                <div className="flex rounded-md border border-ops-border/30 p-0.5">
                  <button type="button" className={`rounded px-2 py-1 text-[9px] font-semibold ${custom ? 'text-ops-muted' : 'bg-ops-text text-ops-bg'}`} onClick={() => setCustomMode(key, false)}>
                    {t('settings.useDefaultPrompt')}
                  </button>
                  <button type="button" className={`rounded px-2 py-1 text-[9px] font-semibold ${custom ? 'bg-ops-text text-ops-bg' : 'text-ops-muted'}`} onClick={() => setCustomMode(key, true)}>
                    {t('settings.useCustomPrompt')}
                  </button>
                </div>
              </div>

              {custom ? (
                <textarea
                  className="field-control mt-3 min-h-[120px] w-full resize-y font-mono text-[10px] leading-5"
                  value={overrides[key]}
                  maxLength={settings.maxPromptChars}
                  onChange={(event) => onChange({ ...overrides, [key]: event.target.value })}
                />
              ) : (
                <pre className="mt-3 max-h-36 overflow-auto whitespace-pre-wrap rounded-md border border-ops-border/20 bg-ops-bg/35 p-3 text-[10px] leading-5 text-ops-muted">{settings.defaults[key] || t('settings.emptyOrganizationRules')}</pre>
              )}

              <div className="mt-2 flex items-center justify-between gap-3 text-[9px] text-ops-muted/70">
                <span>{custom ? `${overrides[key].length}/${settings.maxPromptChars}` : t('settings.systemDefaultActive')}</span>
                <button type="button" className="hover:text-ops-text" onClick={() => setPreviewKey(previewKey === key ? null : key)}>
                  {previewKey === key ? t('settings.hideEffectivePrompt') : t('settings.previewEffectivePrompt')}
                </button>
              </div>
              {previewKey === key ? (
                <pre className="mt-2 max-h-44 overflow-auto whitespace-pre-wrap rounded-md border border-ops-cyan/20 bg-ops-cyan/5 p-3 text-[10px] leading-5 text-ops-text">{effective || t('settings.emptyOrganizationRules')}</pre>
              ) : null}
            </section>
          )
        })}
      </div>

      <footer className="flex flex-wrap items-center justify-between gap-3 pt-2">
        <div className="text-[10px] text-ops-muted">
          {saved ? t('settings.promptsSavedNextRun') : t('settings.promptsRevision', { revision: String(settings.revision) })}
        </div>
        <div className="flex gap-2">
          <button type="button" className="button" disabled={saving} onClick={onReset}>{t('settings.resetAllPrompts')}</button>
          <button type="button" className="button button-primary" disabled={saving} onClick={onSave}>{saving ? t('settings.saving') : t('settings.savePrompts')}</button>
        </div>
      </footer>
    </div>
  )
}
