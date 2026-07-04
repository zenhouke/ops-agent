import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'
import { useTheme } from 'next-themes'
import { translate, type Language, type TranslationKey } from '../i18n/translations'

export type ThemeMode = 'system' | 'dark' | 'light'
export type ResolvedTheme = 'dark' | 'light'

const LANGUAGE_STORAGE_KEY = 'ops-agent-language'
const DEFAULT_LANGUAGE: Language = 'zh-CN'
const DEFAULT_THEME_MODE: ThemeMode = 'system'

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

function getStoredLanguage(): Language {
  if (typeof window === 'undefined') {
    return DEFAULT_LANGUAGE
  }

  const storedLanguage = window.localStorage.getItem(LANGUAGE_STORAGE_KEY)
  return isLanguage(storedLanguage) ? storedLanguage : DEFAULT_LANGUAGE
}

interface AppearanceProviderProps {
  children: React.ReactNode
}

export function AppearanceProvider({ children }: AppearanceProviderProps) {
  const [language, setLanguageState] = useState<Language>(getStoredLanguage)

  // 主题切换逻辑完全委托给 next-themes：
  // - theme 对应用户选择（system / dark / light），映射为 themeMode
  // - resolvedTheme 对应实际生效主题，映射为 resolvedTheme
  // - setTheme 用于切换，映射为 setThemeMode
  // next-themes 负责 no-flash、system 跟随、localStorage 持久化。
  const { theme, resolvedTheme, setTheme } = useTheme()

  const themeMode = (theme as ThemeMode) ?? DEFAULT_THEME_MODE
  const resolved = (resolvedTheme as ResolvedTheme) ?? 'dark'

  useEffect(() => {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, language)
    document.documentElement.lang = language
  }, [language])

  const setLanguage = useCallback((nextLanguage: Language) => {
    setLanguageState(nextLanguage)
  }, [])

  const setThemeMode = useCallback((nextThemeMode: ThemeMode) => {
    setTheme(nextThemeMode)
  }, [setTheme])

  const t = useCallback(
    (key: TranslationKey, values: Record<string, string> = {}) =>
      translate(language, key, values),
    [language],
  )

  const value = useMemo(
    () => ({ language, themeMode, resolvedTheme: resolved, setLanguage, setThemeMode, t }),
    [language, themeMode, resolved, setLanguage, setThemeMode, t],
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
