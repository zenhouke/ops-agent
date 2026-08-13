import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'
import { translate, type Language, type TranslationKey } from '../i18n/translations'

export type ThemeMode = 'system' | 'dark' | 'light'
export type ResolvedTheme = 'dark' | 'light'

const LANGUAGE_STORAGE_KEY = 'ops-agent-language'
const THEME_MODE_STORAGE_KEY = 'ops-agent-theme-mode'
const APPEARANCE_VERSION_STORAGE_KEY = 'ops-agent-appearance-version'
const CURRENT_APPEARANCE_VERSION = '2'
const DEFAULT_LANGUAGE: Language = 'zh-CN'
const DEFAULT_THEME_MODE: ThemeMode = 'dark'

interface AppearanceContextValue {
  language: Language
  themeMode: ThemeMode
  resolvedTheme: ResolvedTheme
  setLanguage: (language: Language) => void
  setThemeMode: (themeMode: ThemeMode) => void
  t: (key: TranslationKey, values?: Record<string, string>) => string
}

const AppearanceContext = createContext<AppearanceContextValue | null>(null)

function isLanguage(value: string | null): value is Language {
  return value === 'zh-CN' || value === 'en-US'
}

function isThemeMode(value: string | null): value is ThemeMode {
  return value === 'system' || value === 'dark' || value === 'light'
}

function getStoredLanguage(): Language {
  if (typeof window === 'undefined') {
    return DEFAULT_LANGUAGE
  }

  const storedLanguage = window.localStorage.getItem(LANGUAGE_STORAGE_KEY)
  return isLanguage(storedLanguage) ? storedLanguage : DEFAULT_LANGUAGE
}

function getStoredThemeMode(): ThemeMode {
  if (typeof window === 'undefined') {
    return DEFAULT_THEME_MODE
  }

  const storedThemeMode = window.localStorage.getItem(THEME_MODE_STORAGE_KEY)
  const appearanceVersion = window.localStorage.getItem(APPEARANCE_VERSION_STORAGE_KEY)

  // Version 1 defaulted to the host system theme. Migrate that inherited default to
  // the desktop workbench's dark theme while preserving an explicit light choice.
  if (appearanceVersion !== CURRENT_APPEARANCE_VERSION && storedThemeMode === 'system') {
    return DEFAULT_THEME_MODE
  }

  return isThemeMode(storedThemeMode) ? storedThemeMode : DEFAULT_THEME_MODE
}

function resolveSystemTheme(): ResolvedTheme {
  if (typeof window === 'undefined') {
    return 'dark'
  }

  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

interface AppearanceProviderProps {
  children: React.ReactNode
}

export function AppearanceProvider({ children }: AppearanceProviderProps) {
  const [language, setLanguageState] = useState<Language>(getStoredLanguage)
  const [themeMode, setThemeModeState] = useState<ThemeMode>(getStoredThemeMode)
  const [systemTheme, setSystemTheme] = useState<ResolvedTheme>(resolveSystemTheme)

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    const handleChange = (event: MediaQueryListEvent) => {
      setSystemTheme(event.matches ? 'dark' : 'light')
    }

    setSystemTheme(mediaQuery.matches ? 'dark' : 'light')
    mediaQuery.addEventListener('change', handleChange)

    return () => {
      mediaQuery.removeEventListener('change', handleChange)
    }
  }, [])

  const resolvedTheme: ResolvedTheme = themeMode === 'system' ? systemTheme : themeMode

  useEffect(() => {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, language)
    document.documentElement.lang = language
  }, [language])

  useEffect(() => {
    window.localStorage.setItem(THEME_MODE_STORAGE_KEY, themeMode)
    window.localStorage.setItem(APPEARANCE_VERSION_STORAGE_KEY, CURRENT_APPEARANCE_VERSION)
  }, [themeMode])

  useEffect(() => {
    document.documentElement.dataset.theme = resolvedTheme
  }, [resolvedTheme])

  const setLanguage = useCallback((nextLanguage: Language) => {
    setLanguageState(nextLanguage)
  }, [])

  const setThemeMode = useCallback((nextThemeMode: ThemeMode) => {
    setThemeModeState(nextThemeMode)
  }, [])

  const t = useCallback(
    (key: TranslationKey, values: Record<string, string> = {}) =>
      translate(language, key, values),
    [language],
  )

  const value = useMemo(
    () => ({ language, themeMode, resolvedTheme, setLanguage, setThemeMode, t }),
    [language, themeMode, resolvedTheme, setLanguage, setThemeMode, t],
  )

  return <AppearanceContext.Provider value={value}>{children}</AppearanceContext.Provider>
}

export function useAppearance() {
  const context = useContext(AppearanceContext)

  if (!context) {
    throw new Error('useAppearance must be used within an AppearanceProvider')
  }

  return context
}
