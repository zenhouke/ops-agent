import { useEffect, useState } from 'react'
import { languages, type Language } from '../../i18n/translations'
import {
  DEFAULT_TERMINAL_BACKGROUND,
  LIGHT_TERMINAL_BACKGROUND,
  normalizeHexColor,
  type ThemeMode,
  useAppearance,
} from '../../hooks/useAppearance'
import type { AppearanceSectionProps } from './settingsTypes'

const themeOptions: ThemeMode[] = ['system', 'dark', 'light']
const terminalBackgroundPresets = [
  { color: '#000000', label: 'settings.terminalPureBlack' },
  { color: '#111110', label: 'settings.terminalWarmGraphite' },
  { color: '#1C1B19', label: 'settings.terminalSoftGraphite' },
  { color: '#24221F', label: 'settings.terminalDeepGray' },
  { color: '#F3F2EF', label: 'settings.terminalWarmLight' },
] as const

function getThemeOptionLabel(themeMode: ThemeMode, t: ReturnType<typeof useAppearance>['t']) {
  if (themeMode === 'system') {
    return t('settings.themeSystem')
  }

  return themeMode === 'dark' ? t('settings.themeDark') : t('settings.themeLight')
}

export function AppearanceSection({ language, themeMode, resolvedTheme, onLanguageChange, onThemeModeChange }: AppearanceSectionProps) {
  const { terminalBackground, terminalBackgroundFollowsTheme, setTerminalBackground, resetTerminalBackground, t } = useAppearance()
  const [customColor, setCustomColor] = useState(terminalBackground)
  const [customColorInvalid, setCustomColorInvalid] = useState(false)
  const themeLabel = resolvedTheme === 'dark' ? t('settings.themeDark') : t('settings.themeLight')
  const followedTerminalBackground = resolvedTheme === 'dark' ? DEFAULT_TERMINAL_BACKGROUND : LIGHT_TERMINAL_BACKGROUND
  const currentThemeLabel = themeMode === 'system'
    ? t('settings.currentThemeWithSystem', { theme: themeLabel })
    : t('settings.currentTheme', { theme: themeLabel })

  useEffect(() => {
    setCustomColor(terminalBackground)
    setCustomColorInvalid(false)
  }, [terminalBackground])

  const applyCustomColor = () => {
    const normalized = normalizeHexColor(customColor)
    setCustomColorInvalid(!normalized)
    if (normalized) {
      setTerminalBackground(normalized)
      setCustomColor(normalized)
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <div className="flex items-center justify-between pb-4 border-b border-ops-border/20">
        <div>
          <h4 className="text-[14px] font-bold text-ops-text">{t('settings.appearance')}</h4>
          <p className="text-[10px] font-medium text-ops-muted mt-1 tracking-wider opacity-60">{t('settings.appearanceDescription')}</p>
        </div>
      </div>

      <section className="bg-ops-deep/40 p-6 rounded-2xl border border-ops-border/20 flex flex-col gap-8">
        <div className="flex flex-col gap-4">
          <div>
            <h5 className="text-[12px] font-bold text-ops-text">{t('settings.language')}</h5>
          </div>
          <div className="flex flex-wrap gap-2">
            {languages.map((option) => (
              <button
                key={option.value}
                type="button"
                className={language === option.value ? 'button-mini button-mini-primary' : 'button-mini'}
                onClick={() => onLanguageChange(option.value as Language)}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-4">
          <div>
            <h5 className="text-[12px] font-bold tracking-[0.12em] text-ops-text">{t('settings.theme')}</h5>
            <p className="text-[10px] font-medium text-ops-muted mt-1 tracking-wider opacity-60">{currentThemeLabel}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {themeOptions.map((option) => (
              <button
                key={option}
                type="button"
                className={themeMode === option ? 'button-mini button-mini-primary' : 'button-mini'}
                onClick={() => onThemeModeChange(option)}
              >
                {getThemeOptionLabel(option, t)}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-4 border-t border-ops-border/20 pt-6">
          <div>
            <h5 className="text-[12px] font-bold tracking-[0.12em] text-ops-text">{t('settings.terminalAppearance')}</h5>
            <p className="mt-1 text-[10px] font-medium tracking-wider text-ops-muted opacity-60">{t('settings.terminalBackgroundDescription')}</p>
          </div>

          <button
            type="button"
            aria-pressed={terminalBackgroundFollowsTheme}
            className={`flex items-center gap-2 rounded-md border px-3 py-2 text-left text-[10px] font-semibold transition ${terminalBackgroundFollowsTheme ? 'border-ops-cyan/65 bg-ops-cyan/10 text-ops-text' : 'border-ops-border/30 text-ops-muted hover:border-ops-border/55 hover:text-ops-text'}`}
            onClick={resetTerminalBackground}
          >
            <span className="flex h-5 w-5 shrink-0 overflow-hidden rounded border border-ops-border/35">
              <span className="h-full w-1/2 bg-[#111110]" />
              <span className="h-full w-1/2 bg-[#F3F2EF]" />
            </span>
            <span>{t('settings.terminalFollowTheme')}</span>
            <span className="ml-auto font-mono text-[9px] opacity-55">{followedTerminalBackground}</span>
          </button>

          <div className="grid gap-2 sm:grid-cols-2">
            {terminalBackgroundPresets.map((preset) => (
              <button
                key={preset.color}
                type="button"
                aria-pressed={!terminalBackgroundFollowsTheme && terminalBackground === preset.color}
                className={`flex items-center gap-2 rounded-md border px-3 py-2 text-left text-[10px] font-semibold transition ${!terminalBackgroundFollowsTheme && terminalBackground === preset.color ? 'border-ops-cyan/65 bg-ops-cyan/10 text-ops-text' : 'border-ops-border/30 text-ops-muted hover:border-ops-border/55 hover:text-ops-text'}`}
                onClick={() => setTerminalBackground(preset.color)}
              >
                <span className="h-5 w-5 shrink-0 rounded border border-ops-border/35" style={{ backgroundColor: preset.color }} />
                <span className="min-w-0 flex-1 truncate">{t(preset.label)}</span>
                <span className="font-mono text-[9px] opacity-55">{preset.color}</span>
              </button>
            ))}
          </div>

          <div className="flex flex-wrap items-start gap-2">
            <input
              type="color"
              value={terminalBackground}
              aria-label={t('settings.terminalColorPicker')}
              className="h-9 w-11 cursor-pointer rounded-md border border-ops-border/35 bg-ops-panel p-1"
              onChange={(event) => setTerminalBackground(event.target.value)}
            />
            <div className="min-w-[180px] flex-1">
              <input
                type="text"
                value={customColor}
                aria-label={t('settings.terminalCustomColor')}
                aria-invalid={customColorInvalid}
                className={`field-control h-9 w-full font-mono uppercase ${customColorInvalid ? 'border-ops-danger/70' : ''}`}
                placeholder="#111110"
                maxLength={7}
                onChange={(event) => {
                  const value = event.target.value
                  setCustomColor(value)
                  const normalized = normalizeHexColor(value)
                  if (normalized) {
                    setTerminalBackground(normalized)
                    setCustomColorInvalid(false)
                  }
                }}
                onBlur={applyCustomColor}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    applyCustomColor()
                  }
                }}
              />
              {customColorInvalid ? <p className="mt-1 text-[10px] text-ops-danger">{t('settings.terminalColorInvalid')}</p> : null}
            </div>
            <button type="button" className="button-mini h-9" onClick={resetTerminalBackground}>
              {t('settings.terminalReset')}
            </button>
          </div>
        </div>
      </section>
    </div>
  )
}
