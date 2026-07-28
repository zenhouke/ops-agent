import { en } from './locales/en'
import { zh } from './locales/zh'

export type Language = 'zh-CN' | 'en-US'

export const languages: Array<{ value: Language; label: string }> = [
  { value: 'zh-CN', label: '中文' },
  { value: 'en-US', label: 'English' },
]

export const translations = Object.fromEntries(
  (Object.keys(zh) as Array<keyof typeof zh>).map((key) => [
    key,
    { 'zh-CN': zh[key], 'en-US': en[key] },
  ]),
) as {
  readonly [K in keyof typeof zh]: {
    readonly 'zh-CN': string
    readonly 'en-US': string
  }
}

export type TranslationKey = keyof typeof translations

export function translate(
  language: Language,
  key: TranslationKey,
  values: Record<string, string> = {},
) {
  const template: string = translations[key]?.[language] ?? key
  return Object.entries(values).reduce<string>(
    (text, [name, value]) => text.split(`{${name}}`).join(value),
    template,
  )
}
